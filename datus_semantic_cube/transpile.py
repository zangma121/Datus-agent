# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Deterministic OSI YAML -> Cube JS transpiler (M8).

One semantic model source for all engines: OSI YAML (natively consumed by
the dosi and metricflow engines) transpires into Cube JS so the cube engine
requires no separately authored models. Deterministic — no LLM; the
descriptions and aliases were authored into the YAML at modeling time and
flow through verbatim.

Mapping (T-D1~T-D3):
- data_source.name        -> cube name (+ sql_query/table as the cube sql)
- measures (agg + expr)   -> measures with sql=expr and type = agg mapped.
  Exprs containing arithmetic operators are DUAL-EMITTED (T-D1):
    * the aggregate leg keeps the OSI name as a ``type: number`` calculated
      measure whose leaf columns are wrapped in their OSI agg — ``a / b``
      aggregates as SUM(a)/SUM(b) (ratio-of-sums, the M5-verified shape),
      with every denominator NULLIF-guarded because Postgres raises on x/0;
    * a row-level ``<Camel>PerRow`` dimension carries the verbatim expr
      (M5 lesson: highest/lowest questions rank per row).
- identifiers[type=PRIMARY] -> primaryKey dimension; the same identifier
  name across 2+ cubes auto-generates belongsTo joins (alphabetically later
  cube points to the earlier one)
- dimensions[type=TIME]   -> plain dimensions (fake primary-time columns
  from BIRD-style snapshots pass through harmlessly)
- description             -> description; omitted entirely when empty
- sections the transpiler does not consume (mutability, doc-level keys, ...)
  are listed in the report's ``ignored`` field (T-D3), never silently lost
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from datus.utils.loggings import get_logger
from datus_semantic_cube.generate import lint_model_text, render_aliases_meta
from datus_semantic_cube.naming import camel as _camel
from datus_semantic_cube.naming import normalize_join_name as _normalize_join_name

logger = get_logger(__name__)

# OSI agg -> Cube measure type.
_AGG_MAP = {
    "sum": "sum",
    "average": "average",
    "avg": "average",
    "count": "count",
    "count_distinct": "count_distinct",
    "countdistinct": "count_distinct",
    "min": "min",
    "max": "max",
}

# data_source keys the transpiler consumes; anything else is reported ignored.
_CONSUMED_DS_KEYS = {"name", "description", "sql_query", "table", "identifiers", "measures", "dimensions"}

_BARE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The exact shapes _wrap_leaf emits — used to find denominators afterwards.
_WRAPPED_AGG = (
    r'(?:SUM|AVG)\(CAST\("[A-Za-z_][A-Za-z0-9_]*" AS DOUBLE PRECISION\)\)'
    r'|COUNT\(DISTINCT "[A-Za-z_][A-Za-z0-9_]*"\)'
    r'|(?:COUNT|MIN|MAX)\("[A-Za-z_][A-Za-z0-9_]*"\)'
)

# A column reference that may carry spaces (spaced physical column names) —
# safe to double-quote whole; anything with parens/operators is an expression.
_PLAIN_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*$")


def _quote_leaves(expr: str, leaves: Set[str]) -> str:
    """Double-quote every known leaf-column token in the expr — unquoted
    mixed-case identifiers fold to lowercase in Postgres and stop resolving."""
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr)) & leaves
    result = expr
    for col in sorted(tokens, key=len, reverse=True):
        result = re.sub(rf"\b{re.escape(col)}\b", lambda m: f'"{m.group(0)}"', result)
    return result


def _wrap_leaf(col: str, agg: str) -> str:
    """One leaf column (quoted, case-preserving) wrapped in its OSI aggregation."""
    a = _AGG_MAP.get(agg.lower(), "sum")
    if a == "count_distinct":
        return f'COUNT(DISTINCT "{col}")'
    fn = {"sum": "SUM", "average": "AVG", "avg": "AVG", "count": "COUNT", "min": "MIN", "max": "MAX"}.get(a, "SUM")
    if fn in ("SUM", "AVG"):
        return f'{fn}(CAST("{col}" AS DOUBLE PRECISION))'
    return f'{fn}("{col}")'


def _wrap_leaf_columns(expr: str, leaves: Set[str], agg: str) -> str:
    """Aggregate-leg construction for a dual-emit measure (T-D1): wrap each
    known leaf column in its OSI aggregation — ``a / b`` with agg SUM becomes
    ``SUM(CAST(a AS DOUBLE PRECISION)) / NULLIF(SUM(CAST(b ...)), 0)`` — and
    NULLIF-guard every wrapped aggregate in a denominator position. Unknown
    tokens pass through untouched."""
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr)) & leaves
    result = expr
    for col in sorted(tokens, key=len, reverse=True):
        result = re.sub(rf"\b{re.escape(col)}\b", lambda _m, c=col: _wrap_leaf(c, agg), result)
    return re.sub(rf"/\s*({_WRAPPED_AGG})", r"/ NULLIF(\1, 0)", result)


def _unique_member(member: str, taken: Set[str]) -> str:
    """Deterministic de-clash: first collision-free numeric suffix."""
    candidate, n = member, 2
    while candidate in taken:
        candidate = f"{member}{n}"
        n += 1
    taken.add(candidate)
    return candidate


def load_osi_models(yaml_dir: str) -> List[Dict[str, Any]]:
    """Load every ``*.yml``/``*.yaml`` file in the directory as an OSI model.

    Doc-level keys other than ``data_source`` are recorded on the model as
    ``_doc_ignored`` so the report can name them."""
    models: List[Dict[str, Any]] = []
    for path in sorted(Path(yaml_dir).glob("*.y*ml")):
        with open(path) as f:
            doc = yaml.safe_load(f) or {}
        ds = doc.get("data_source")
        if not ds:
            logger.warning("Skipping %s: no data_source section", path.name)
            continue
        ds["_doc_ignored"] = sorted(k for k in doc if k != "data_source")
        models.append(ds)
    return models


def _has_operator(expr: str) -> bool:
    """True when the expression computes something (contains arithmetic
    operators outside of single quotes)."""
    stripped = re.sub(r"'[^']*'", "", expr)
    return bool(re.search(r"[+\-*/]", stripped))


_PREAGGREGATED = re.compile(r"\b(SUM|AVG|COUNT|MIN|MAX)\s*\(", re.IGNORECASE)


def _is_preaggregated(expr: str) -> bool:
    """True when the expr already contains an aggregate call — Cube wraps
    typed measures in its own aggregate, so emitting it verbatim under a
    type: sum would double-aggregate (M5 lesson)."""
    return bool(_PREAGGREGATED.search(expr))


def _leaf_pool(osi: Dict[str, Any]) -> Set[str]:
    """Column names a derived measure's expr may legitimately reference:
    identifier columns, pure (operator-free) measure exprs, and bare
    dimension exprs."""
    leaves: Set[str] = set()
    for ident in osi.get("identifiers") or []:
        col = str(ident.get("expr") or ident.get("name") or "").strip()
        if col:
            leaves.add(col)
    for m in osi.get("measures") or []:
        expr = str(m.get("expr") or "").strip()
        if expr and not _has_operator(expr):
            leaves.add(expr)
    for d in osi.get("dimensions") or []:
        expr = str(d.get("expr") or d.get("name") or "").strip()
        if _BARE_IDENT.match(expr):
            leaves.add(expr)
    return leaves


def transpile_model(osi: Dict[str, Any], joins_code: str = "") -> str:
    """Render one OSI ``data_source`` dict into cube JS (pure rendering —
    linting happens once in transpile_dir)."""
    name = str(osi.get("name") or "cube")
    cube_name = _camel(name).title() or "Cube"
    sql = (osi.get("sql_query") or "").strip() or f"SELECT * FROM {name}"

    taken: Set[str] = set()
    dims: List[str] = []
    count_member = _unique_member(_camel(name) + "Count", taken)
    measures: List[str] = [f"    {count_member}: {{ sql: `1`, type: `count` }},"]

    for ident in osi.get("identifiers") or []:
        col = str(ident.get("expr") or ident.get("name") or "")
        desc = str(ident.get("description") or "")
        desc_js = json.dumps(desc, ensure_ascii=True) if desc else None
        parts = [f'sql: `"{col}"`', "type: `string`"]
        if str(ident.get("type") or "").upper() == "PRIMARY":
            parts.append("primaryKey: true")
        if desc_js is not None:
            parts.append(f"description: {desc_js}")
        member = _unique_member(_camel(col), taken)
        dims.append(f"    {member}: {{ {', '.join(parts)} }},")

    leaves = _leaf_pool(osi)
    for m in osi.get("measures") or []:
        m_name = str(m.get("name") or "")
        member = _camel(m_name)
        if member in taken:  # M7 idiom: measures yield to dimensions w/ Total
            member = _unique_member(member + "Total", taken)
        else:
            taken.add(member)
        agg = str(m.get("agg") or "sum").lower()
        expr = str(m.get("expr") or "").strip()
        desc = str(m.get("description") or "")
        aliases = m.get("aliases") or []
        if aliases:
            desc = (desc + "\n" if desc else "") + "Aliases: " + ", ".join(str(a) for a in aliases)
        desc_js = json.dumps(desc, ensure_ascii=True) if desc else None
        desc_part = f", description: {desc_js}" if desc_js is not None else ""
        meta_part = render_aliases_meta(aliases)
        meta_part = f", {meta_part}" if meta_part else ""

        if _has_operator(expr):
            # Dual emission (T-D1): aggregate leg wraps leaves in their OSI
            # agg (ratio-of-sums, NULLIF-guarded); the verbatim expr (leaves
            # quoted) becomes a row-level PerRow dimension for per-row ranking.
            measures.append(
                f"    {member}: {{ sql: `{_wrap_leaf_columns(expr, leaves, agg)}`, type: `number`{desc_part}{meta_part} }},"
            )
            dim_member = _unique_member(member + "PerRow", taken)
            d_desc = f"{desc} ROW-LEVEL (per row)." if desc else "ROW-LEVEL expression."
            d_desc_js = json.dumps(d_desc, ensure_ascii=True)
            dims.append(
                f"    {dim_member}: {{ sql: `{_quote_leaves(expr, leaves)}`, type: `number`, "
                f"description: {d_desc_js} }},"
            )
        elif _is_preaggregated(expr):
            # Author already aggregated in the expr: emit as a calculated
            # measure, never under a type that Cube would aggregate again.
            logger.warning("Measure %s.%s expr is pre-aggregated; emitted verbatim as type: number", cube_name, member)
            measures.append(f"    {member}: {{ sql: `{expr}`, type: `number`{desc_part}{meta_part} }},")
        else:
            ctype = _AGG_MAP.get(agg, "number")
            # Strictly-typed backends (Postgres) reject SUM over text columns
            # and fold unquoted mixed-case identifiers to lowercase — quote
            # bare column refs and cast numeric aggs (M7 live-model shape).
            col_ref = f'"{expr}"' if _BARE_IDENT.match(expr) else expr
            sql_out = f"CAST({col_ref} AS DOUBLE PRECISION)" if ctype in ("sum", "average") else col_ref
            measures.append(f"    {member}: {{ sql: `{sql_out}`, type: `{ctype}`{desc_part}{meta_part} }},")

    for d in osi.get("dimensions") or []:
        d_name = str(d.get("name") or "")
        col = str(d.get("expr") or d_name)
        # Quote plain column references (incl. spaced names) so case and
        # spaces survive; expressions (function calls etc.) pass through.
        col_ref = f'"{col}"' if _PLAIN_COLUMN.match(col) else col
        dtype = "time" if str(d.get("type") or "").upper() == "TIME" else "string"
        desc = str(d.get("description") or "")
        desc_js = json.dumps(desc, ensure_ascii=True) if desc else None
        parts = [f"sql: `{col_ref}`", f"type: `{dtype}`"]
        if desc_js is not None:
            parts.append(f"description: {desc_js}")
        member = _unique_member(_camel(d_name), taken)
        dims.append("    " + member + ": { " + ", ".join(parts) + " },")

    join_block = f"\n  joins: {{\n{joins_code}\n  }}," if joins_code.strip() else ""
    lines = [
        f"cube(`{cube_name}`, {{",
        f"  sql: `{sql}`," + join_block,
        "  measures: {",
        *measures,
        "  },",
        "  dimensions: {",
        *dims,
        "  },",
        "});",
    ]
    return "\n".join(lines)


def _infer_identifier_joins(models: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Same-name PRIMARY identifier across cubes -> belongsTo joins on the
    alphabetically later cube (M7-verified pattern).

    Returns ``{cube_name: {parent_cube_name: join_code}}``."""
    primaries: Dict[str, str] = {}
    for ds in models:
        name = str(ds.get("name") or "")
        for ident in ds.get("identifiers") or []:
            if str(ident.get("type") or "").upper() == "PRIMARY":
                primaries[name] = str(ident.get("expr") or ident.get("name") or "")
                break

    edges: Dict[str, Dict[str, str]] = {}
    names = sorted(primaries)
    for i, parent in enumerate(names):
        for child in names[i + 1:]:
            parent_col, child_col = primaries[parent], primaries[child]
            if not (_normalize_join_name(parent_col) and _normalize_join_name(parent_col) == _normalize_join_name(child_col)):
                continue
            parent_cube = _camel(parent).title() or "Cube"
            block = (
                f"    {parent_cube}: {{ sql: "
                f"`${{CUBE}}.\"{child_col}\" = "
                f"`${{{parent_cube}}}.\"{parent_col}\"`, "
                f"relationship: `belongsTo` }}"
            )
            edges.setdefault(child, {})[parent] = block
    return edges


def _ignored_sections(ds: Dict[str, Any]) -> List[str]:
    """Sections present in the YAML but not consumed by the transpiler."""
    return sorted(
        {*(k for k in ds.get("_doc_ignored", [])), *(k for k in ds if k not in _CONSUMED_DS_KEYS and not k.startswith("_"))}
    )


def transpile_dir(yaml_dir: str, out_dir: Optional[str] = None, overwrite: bool = False):
    """Transpile every OSI model in ``yaml_dir``; lint once per model, write
    ``<name>.js`` files plus ``_generation_report.json`` when ``out_dir`` is
    given, and return one result dict per model."""
    models = load_osi_models(yaml_dir)
    join_map = _infer_identifier_joins(models)
    out_path = Path(out_dir) if out_dir else None
    results = []
    for ds in models:
        name = str(ds.get("name") or "cube")
        joins_code = "\n".join(join_map.get(name, {}).values())
        js = transpile_model(ds, joins_code=joins_code)
        ok, issues = lint_model_text(js)
        status = "generated"
        if out_path is not None:
            target = out_path / f"{name}.js"
            if target.exists() and not overwrite:
                status = "skipped"
            else:
                out_path.mkdir(parents=True, exist_ok=True)
                target.write_text(js)
        if not ok:
            status = "lint_failed"
        report = {"status": status, "lint": {"ok": ok, "issues": issues},
                  "joins": {k: "belongsTo" for k in join_map.get(name, {})},
                  "ignored": _ignored_sections(ds)}
        results.append({"table_name": name, "js_text": js, "report": report})

    if out_path is not None:
        (out_path / "_generation_report.json").write_text(
            json.dumps({r["table_name"]: r["report"] for r in results}, indent=1, ensure_ascii=False)
        )
    return results
