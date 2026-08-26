# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Policy runtime for the gienbi-policy plugin.

Implements the Datus policy lifecycle hooks against GienBI's permission
model. ``before_sql_read`` / ``after_read_result`` (row filters and column
masking) land in T4.5/T4.6; the base object carries them as explicit
pass-throughs so the runtime contract stays complete.
"""

from typing import Any, Dict, List

from datus.utils.loggings import get_logger

from datus_gienbi_policy import row_rules
from datus_gienbi_policy.permissions import PermissionReader

logger = get_logger(__name__)

#: Sentinel: rules exist but none convertible — callers must deny.
_DENY = object()


def create_runtime(profile: Dict[str, Any]) -> "GienbiPolicyRuntime":
    """Plugin policy factory: profile comes from agent.yml plugin config."""
    return GienbiPolicyRuntime(profile)


class GienbiPolicyRuntime:
    def __init__(self, profile: Dict[str, Any]):
        self.multi_tenant = bool(profile.get("multi_tenant", False))
        self.engine = str(profile.get("engine", "metricflow"))
        connection_factory = profile.get("connection_factory")
        if connection_factory is None:
            connection_factory = self._mysql_factory(profile)
        self.reader = PermissionReader(
            connection_factory=connection_factory,
            ttl_seconds=float(profile.get("permission_cache_ttl_seconds", 60)),
        )

    @staticmethod
    def _mysql_factory(profile: Dict[str, Any]):
        """Build a MySQL-backed factory from the plugin profile.

        Kept lazy so unit tests never import pymysql; production profiles
        carry the GienBI shared-DB connection settings.
        """
        def factory():
            import pymysql

            return _DictCursorShim(
                pymysql.connect(
                    host=profile.get("mysql_host", "127.0.0.1"),
                    port=int(profile.get("mysql_port", 3306)),
                    user=profile.get("mysql_user", ""),
                    password=profile.get("mysql_password", ""),
                    database=profile.get("mysql_database", ""),
                    charset="utf8mb4",
                )
            )
        return factory

    # ── identity ─────────────────────────────────────────────────────

    def _identity(self, policy_context: Dict[str, Any]):
        org = str(policy_context.get("gienbi_org_id") or "").strip()
        user = str(policy_context.get("gienbi_user_id") or "").strip()
        return org, user

    # ── hooks ────────────────────────────────────────────────────────

    def validate_context(self, policy_context: Dict[str, Any]) -> Dict[str, Any]:
        org, user = self._identity(policy_context)
        if self.multi_tenant and (not org or not user):
            return {
                "allowed": False,
                "reason": "Multi-tenant deployment requires GienBI org/user identity in policy_context.",
            }
        return {"allowed": True}

    def before_metric_read(
        self,
        metric_names: List[str],
        *,
        datasource: str,
        policy_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        org, user = self._identity(policy_context)
        if self.multi_tenant and (not org or not user):
            return {"allowed": False, "reason": "Missing GienBI identity", "allowed_metrics": [], "denied": []}

        if self.reader.is_org_owner(org, user):
            return {"allowed": True, "allowed_metrics": list(metric_names), "denied": []}

        allowed: List[str] = []
        denied: List[Dict[str, str]] = []
        for name in metric_names:
            if self.reader.view_permission(org, user, "METRIC", name):
                allowed.append(name)
            else:
                denied.append({"metric": name, "reason": "no VIEW permission on metric"})
        return {"allowed": True, "allowed_metrics": allowed, "denied": denied}

    def before_sql_read(self, sql: str, *, datasource: str, dialect: str, policy_context: Dict[str, Any]):
        """Row-level scope, dispatched by engine (T4.5).

        metricflow: rewrite the SQL with sqlglot (deny when not expressible).
        cube: leave the SQL untouched but export ``row_filters`` for the
        adapter to inject into the Cube query payload.
        """
        org, user = self._identity(policy_context)
        if self.multi_tenant and (not org or not user):
            return {"allowed": False, "reason": "Missing GienBI identity", "applied_policies": []}

        if org and user and self.reader.is_org_owner(org, user):
            return {"allowed": True, "sql": sql, "applied_policies": []}

        engine = self.engine
        cond = self._row_condition(sql, org, user, model_names := [])
        if cond is _DENY:
            return {
                "allowed": False,
                "reason": "Row permission rules exist but none could be converted (deny by default).",
                "applied_policies": ["gienbi_row_scope"],
            }
        if cond is None:
            return {"allowed": True, "sql": sql, "applied_policies": []}

        if engine == "cube":
            cube_name = (model_names[0] if model_names else "") or self._cube_name_from_sql(sql)
            filters = row_rules.to_cube_filters(cond, cube_name)
            if not filters:
                return {
                    "allowed": False,
                    "reason": "Row permission rules cannot be expressed as Cube filters (deny by default).",
                    "applied_policies": ["gienbi_row_scope"],
                }
            return {
                "allowed": True,
                "sql": sql,
                "row_filters": filters,
                "applied_policies": ["gienbi_row_scope"],
            }

        rewritten = self._rewrite_sql(sql, cond, dialect)
        if rewritten is None:
            return {
                "allowed": False,
                "reason": "Row permission rules could not be applied to the SQL (deny by default).",
                "applied_policies": ["gienbi_row_scope"],
            }
        return {"allowed": True, "sql": rewritten, "applied_policies": ["gienbi_row_scope"]}

    # ── row-scope pieces ─────────────────────────────────────────────

    @staticmethod
    def _cube_name_from_sql(sql: str) -> str:
        try:
            import sqlglot

            for table in sqlglot.parse_one(sql).find_all(sqlglot.exp.Table):
                return table.name
        except Exception:
            pass
        return ""

    def _row_condition(self, sql: str, org: str, user: str, model_names: List[str] = None):
        """Compose row rules over the tables referenced by the SQL.

        ``model_names`` (optional out-param) collects the canonical GienBI
        ``en_name`` per governed table so the cube path can prefix members.
        """
        if model_names is None:
            model_names = []
        tables = self._cube_name_from_sql_candidates(sql)
        lowered = {t.lower(): t for t in tables}
        conds = []
        for sql_table in tables:
            rules = self.reader.row_rules(org, user, sql_table)
            if not rules.exists:
                # Retry case-insensitively: sqlglot lowercases identifiers
                # while GienBI model names are usually CamelCase.
                canonical = lowered.get(sql_table.lower())
                if canonical:
                    rules = self.reader.row_rules(org, user, canonical)
            if not rules.exists or rules.read_failed:
                if rules.read_failed:
                    return _DENY
                continue
            model_names.append(rules.model_name or sql_table)
            table_cond = None
            for script in rules.scripts:
                converted = row_rules.convert_rule_tree(script)
                if converted is None:
                    return _DENY
                table_cond = converted if table_cond is None else row_rules.Cond(
                    children=[table_cond, converted], branch_op=rules.operator
                )
            if table_cond is not None:
                conds.append(table_cond)
        if not conds:
            return None
        if len(conds) == 1:
            return conds[0]
        return row_rules.Cond(children=conds, branch_op="AND")

    def _cube_name_from_sql_candidates(self, sql: str) -> List[str]:
        try:
            import sqlglot

            return [t.name for t in sqlglot.parse_one(sql).find_all(sqlglot.exp.Table)]
        except Exception:
            return []

    def _rewrite_sql(self, sql: str, cond, dialect: str):
        try:
            import sqlglot

            parsed = sqlglot.parse_one(sql)
            table_name = ""
            for table in parsed.find_all(sqlglot.exp.Table):
                table_name = table.name
                break
            expression = row_rules.to_sqlglot_condition(cond, table_name)
            if expression is None:
                return None
            parsed = parsed.where(expression, copy=False)
            return parsed.sql(dialect=dialect or None)
        except Exception:
            return None

    def after_read_result(self, result: Any, *, sql: str, datasource: str, dialect: str, policy_context: Dict[str, Any]):
        """T4.6: drop forbidden columns from row results with warnings.

        ``result`` is a list of row dicts (the datus read-result shape);
        anything else passes through untouched.
        """
        org, user = self._identity(policy_context)
        forbidden = self.reader.forbidden_columns(org, user)
        if not forbidden or not isinstance(result, list) or not result:
            return {"allowed": True, "result": result, "masked_warnings": []}

        forbidden_set = {c.lower() for c in forbidden}
        masked_rows = []
        warnings: List[str] = []
        present = set()
        for row in result:
            if not isinstance(row, dict):
                return {"allowed": True, "result": result, "masked_warnings": []}
            dropped = {k for k in row.keys() if k.lower() in forbidden_set}
            present.update(dropped)
            masked_rows.append({k: v for k, v in row.items() if k.lower() not in forbidden_set})
        if present:
            warnings = [f"masked forbidden column: {col}" for col in sorted(present)]
            logger.info("GienBI column policy masked: %s", ", ".join(sorted(present)))
        return {"allowed": True, "result": masked_rows, "masked_warnings": warnings}


class _DictCursorShim:
    """pymysql connection with ``execute(sql, params) -> list[dict]``."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params) -> List[Dict[str, Any]]:
        with self._conn.cursor(pymysql_cur()) as cursor:
            rows = cursor.execute(sql, params) or []
            return [dict(row) for row in rows]


def pymysql_cur():
    import pymysql.cursors

    return pymysql.cursors.DictCursor
