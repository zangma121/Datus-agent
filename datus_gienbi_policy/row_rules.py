# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Convert GienBI row-permission rule trees into engine-agnostic conditions.

Input: ``rel_subject_rows.script`` JSON trees (``ruleType`` AND/OR with
``children`` of ``{columnId, op, value}``). Output: a simple ``Condition``
tree both engines consume — metricflow via sqlglot SQL composition, cube
via query filters. A rule present but not convertible yields ``None`` and
the caller denies (chat2agent's deny-by-default).
"""

from typing import Any, Dict, List, Optional

# rule op -> (sqlglot operator, cube operator)
_OP_MAP = {
    "eq": ("=", "equals"),
    "ne": ("<>", "notEquals"),
    "in": ("IN", "in"),
    "gt": (">", "afterDate"),
    "ge": (">=", "afterOrEqualsDate"),
    "lt": ("<", "beforeDate"),
    "le": ("<=", "beforeOrEqualsDate"),
}


class Cond:
    """Leaf: one column comparison; Branch: AND/OR over children."""

    __slots__ = ("column", "op", "value", "children", "branch_op")

    def __init__(self, column=None, op=None, value=None, children=None, branch_op="AND"):
        self.column = column
        self.op = op
        self.value = value
        self.children = children
        self.branch_op = branch_op

    @property
    def is_branch(self) -> bool:
        return self.children is not None


def convert_rule_tree(script: Dict[str, Any]) -> Optional[Cond]:
    """Convert one rule script; ``None`` = not convertible (deny).

    Any child present but unconvertible makes the whole script
    unconvertible — dropping it silently would widen the rule
    (deny-by-default, per chat2agent semantics).
    """
    children_raw = script.get("children") or []
    if not children_raw:
        return None
    converted: List[Cond] = []
    for child in children_raw:
        if not isinstance(child, dict):
            return None
        if "children" in child and child.get("children") is not None:
            nested = convert_rule_tree(child)
            if nested is None:
                return None
            converted.append(nested)
            continue
        leaf = _convert_leaf(child)
        if leaf is None:
            return None
        converted.append(leaf)
    if len(converted) == 1:
        return converted[0]
    branch_op = str(script.get("ruleType") or "AND").upper()
    return Cond(children=converted, branch_op="OR" if branch_op == "OR" else "AND")


def _convert_leaf(child: Dict[str, Any]) -> Optional[Cond]:
    column = str(child.get("columnId") or "").strip()
    op = str(child.get("op") or "").strip().lower()
    value = child.get("value")
    if not column or op not in _OP_MAP or value is None:
        return None
    if op == "in" and not isinstance(value, list):
        value = [value]
    return Cond(column=column, op=op, value=value)


# ── engine projections ─────────────────────────────────────────────────


def to_sqlglot_condition(cond: Cond, table_name: str):
    """Project onto a sqlglot expression against ``table_name``."""
    import sqlglot
    from sqlglot import condition as sqlcond

    def project(node: Cond):
        if node.is_branch:
            parts = [project(c) for c in node.children]
            glue = " OR " if node.branch_op == "OR" else " AND "
            text = glue.join(f"({p.sql()})" for p in parts)
            return sqlcond(text)
        column = f"{table_name}.{node.column}" if table_name else node.column
        sql_op, _ = _OP_MAP[node.op]
        if node.op == "in":
            values = ", ".join(f"'{v}'" for v in node.value)
            return sqlcond(f"{column} IN ({values})")
        value = node.value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            literal = str(value)
        else:
            literal = "'" + str(value).replace("'", "''") + "'"
        return sqlcond(f"{column} {sql_op} {literal}")

    return sqlglot.exp.condition(project(cond).sql())


def to_cube_filters(cond: Cond, cube_name: str) -> List[Dict[str, Any]]:
    """Project onto Cube query filter dicts (member/operator/values)."""
    filters: List[Dict[str, Any]] = []

    def project(node: Cond):
        if node.is_branch:
            # Cube has no nested boolean filter in this simple projection;
            # flatten AND branches, raise on OR below top level.
            if node.branch_op == "OR":
                filters.append({"__or__": [c for c in node.children]})
            else:
                for child in node.children:
                    project(child)
            return
        _, cube_op = _OP_MAP[node.op]
        values = node.value if isinstance(node.value, list) else [node.value]
        filters.append(
            {"member": f"{cube_name}.{node.column}", "operator": cube_op, "values": [str(v) for v in values]}
        )

    project(cond)
    expanded = []
    for f in filters:
        if "__or__" in f:
            # Top-level OR over same-column equals: emit one IN filter.
            leaves = f["__or__"]
            if leaves and all(leaf.op == "eq" and leaf.column == leaves[0].column for leaf in leaves):
                values = [str(leaf.value) for leaf in leaves]
                expanded.append(
                    {"member": f"{cube_name}.{leaves[0].column}", "operator": "equals", "values": values}
                )
            else:
                # Mixed OR we cannot flatten — treat as unconvertible.
                return []
        else:
            expanded.append(f)
    return expanded
