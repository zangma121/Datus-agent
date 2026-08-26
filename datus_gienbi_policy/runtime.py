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

from datus_gienbi_policy.permissions import PermissionReader

logger = get_logger(__name__)


def create_runtime(profile: Dict[str, Any]) -> "GienbiPolicyRuntime":
    """Plugin policy factory: profile comes from agent.yml plugin config."""
    return GienbiPolicyRuntime(profile)


class GienbiPolicyRuntime:
    def __init__(self, profile: Dict[str, Any]):
        self.multi_tenant = bool(profile.get("multi_tenant", False))
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
        # Row-level filters: T4.5 (sqlglot rewrite for metricflow engine,
        # Cube filter injection for the cube engine).
        return {"allowed": True, "sql": sql, "applied_policies": []}

    def after_read_result(self, result: Any, *, sql: str, datasource: str, dialect: str, policy_context: Dict[str, Any]):
        # Column masking: T4.6 (rel_subject_columns forbidden columns).
        return {"allowed": True, "result": result, "applied_policies": []}


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
