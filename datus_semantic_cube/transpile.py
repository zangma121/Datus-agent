# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Deterministic OSI YAML -> Cube JS transpiler (M8).

One semantic model source for all engines: OSI YAML (natively consumed by
the dosi and metricflow engines) transpiles into Cube JS so the cube engine
requires no separately authored models. Deterministic — no LLM; the
descriptions and aliases were authored into the YAML at modeling time and
flow through verbatim.

Mapping (T-D1~T-D3):
- data_source.name        -> cube name (+ sql_query/table as the cube sql)
- measures (agg + expr)   -> measures with sql=expr and type = agg mapped;
  exprs containing arithmetic operators are DUAL-EMITTED: the aggregate
  member keeps the OSI name with leaf columns wrapped in their OSI agg, and
  a row-level ``<Camel>PerRow`` dimension carries the verbatim division
  (M5 lesson: highest/lowest questions rank per row)
- identifiers[type=PRIMARY] -> primaryKey dimension; the same identifier
  name across 2+ cubes auto-generates belongsTo joins (alphabetically later
  cube points to the earlier one)
- dimensions[type=TIME]   -> plain dimensions (fake primary-time columns
  from BIRD-style snapshots pass through harmlessly)
- description             -> description; omitted entirely when empty
"""

from pathlib import Path
from typing import Any, Dict, List

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from datus.utils.loggings import get_logger
from datus_semantic_cube.generate import lint_model_text

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

_JS_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_OPS_HINT = re.compile(r"[*/+-]")


def _camel(name: str) -> str:
    if "_" not in name and " " not in name and name and name[0].isalpha() and _JS_IDENT.match(name):
        return name
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    out = "".join(p[:1].upper() + p[1:] for p in parts)
    out = out[0].lower() + out[1:] if out else "col"
    if not _JS_IDENT.match(out):
        out = "member_" + "".join(ch for ch in out if ch.isalnum())
    return out


def load_osi_models(yaml_dir: str) -> List[Dict[str, Any]]:
    """Load every ``*.yml``/``*.yaml`` file in the directory as an OSI model."""
    models: List[Dict[str, Any]] = []
    for path in sorted(Path(yaml_dir).glob("*.y*ml")):
        with open(path) as f:
            doc = yaml.safe_load(f)
        ds = (doc or {}).get("data_source")
        if not ds:
            logger.warning("Skipping %s: no data_source section", path.name)
            continue
        models.append(ds)
    return models


def _has_operator(expr: str) -> bool:
    """True when the expression computes something (contains arithmetic
    operators outside of quotes)."""
    import re as _re

    stripped = _re.sub(r"'[^']*'", "", expr)
    return bool(_re.search(r"[+\-*/]", stripped))


def _wrap_leaf_columns(expr: str, columns: Dict[str, str], agg: str) -> str:
    """Wrap bare leaf-column references with their OSI aggregation.

    ``a / b`` with agg SUM becomes ``SUM(CAST(a AS DOUBLE)) / NULLIF(SUM(...), 0)``
    (aggregate-level ratio). Leaf = any token that is a known column."""
    import re as _re

    known = {c for c in columns}
    zero_safe = agg.lower() in ("sum", "count", "count_distinct")

    def repl(m: _re.Match) -> str:
        col = m.group(0)
        cast = f"CAST({col} AS DOUBLE PRECISION)"
        wrapped = f"{agg.upper()}({cast})"
        if zero_safe:
            return wrapped
        return f"COALESCE({wrapped}, 0)"

    tokens = set(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr))
    result = expr
    for col in sorted(tokens & known, key=len, reverse=True):
        result = _re.sub(rf"\b{ _re.escape(col) }\b", repl, result)
    return result


def transpile_model(osi: Dict[str, Any], joins_code: str = "") -> str:
    """Render one OSI ``data_source`` dict into cube JS."""
    name = str(osi.get("name") or "cube")
    cube_name = _camel(name).title() or "Cube"
    sql = (osi.get("sql_query") or "").strip() or f"SELECT * FROM {name}"

    pk = None
    for ident in osi.get("identifiers") or []:
        if str(ident.get("type") or "").upper() == "PRIMARY":
            pk = str(ident.get("expr") or ident.get("name") or "")
            break

    dims: List[str] = []
    measures: List[str] = [f"    {_camel(name)}Count: {{ sql: `1`, type: `count` }},"]
    measure_names: List[str] = [_camel(name) + "Count"]

    for ident in osi.get("identifiers") or []:
        col = str(ident.get("expr") or ident.get("name") or "")
        desc = str(ident.get("description") or "")
        desc_js = json.dumps(desc, ensure_ascii=True) if desc else None
        parts = [f'sql: `"{col}"`', "type: `string`"]
        if str(ident.get("type") or "").upper() == "PRIMARY":
            parts.append("primaryKey: true")
        if desc_js is not None:
            parts.append(f"description: {desc_js}")
        dims.append(f"    {_camel(col)}: {{ {', '.join(parts)} }},")

    for m in osi.get("measures") or []:
        m_name = str(m.get("name") or "")
        member = _camel(m_name)
        agg = str(m.get("agg") or "sum").lower()
        ctype = _AGG_MAP.get(agg, "number")
        expr = str(m.get("expr") or "").strip()
        desc = str(m.get("description") or "")
        aliases = m.get("aliases") or []
        if aliases:
            desc = (desc + "\n" if desc else "") + "Aliases: " + ", ".join(str(a) for a in aliases)
        desc_js = json.dumps(desc, ensure_ascii=True) if desc else None
        desc_part = f", description: {desc_js}" if desc_js is not None else ""
        measures.append(
            f"    {member}: {{ sql: `{expr}`, type: `{ctype}`{desc_part} }},"
        )
        measure_names.append(member)

        if _has_operator(expr):
            # Dual emission: the verbatim expr as a row-level dimension with
            # a PerRow suffix (M5: highest/lowest questions rank per row).
            dim_member = member + "PerRow"
            d_desc = f"{desc} ROW-LEVEL (per row)." if desc else "ROW-LEVEL expression."
            d_desc_js = json.dumps(d_desc, ensure_ascii=True)
            dims.append(
                f"    {dim_member}: {{ sql: `{expr}`, type: `number`, "
                f"description: {d_desc_js} }},"
            )

    for d in osi.get("dimensions") or []:
        d_name = str(d.get("name") or "")
        member = _camel(d_name)
        col = str(d.get("expr") or d_name)
        dtype = "time" if str(d.get("type") or "").upper() == "TIME" else "string"
        desc = str(d.get("description") or "")
        desc_js = json.dumps(desc, ensure_ascii=True) if desc else None
        parts = [f'sql: `{col}`', f"type: `{dtype}`"]
        if desc_js is not None:
            parts.append(f"description: {desc_js}")
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
    js = "\n".join(lines)
    ok, issues = lint_model_text(js)
    if not ok:
        logger.warning("Transpiled cube %s failed lint: %s", cube_name, issues)
    return js


def _infer_identifier_joins(models: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Same-name PRIMARY identifier across cubes -> belongsTo joins on the
    alphabetically later cube (M7-verified pattern)."""
    primaries: Dict[str, Dict[str, str]] = {}
    for ds in models:
        name = str(ds.get("name") or "")
        for ident in ds.get("identifiers") or []:
            if str(ident.get("type") or "").upper() == "PRIMARY":
                primaries[name] = {
                    "expr": str(ident.get("expr") or ident.get("name") or ""),
                    "member": _camel(str(ident.get("expr") or ident.get("name") or "")),
                }
                break

    edges: Dict[str, Dict[str, str]] = {}
    names = sorted(primaries)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            lp, rp = primaries[left], primaries[right]
            import re as _re

            nl = _re.sub(r"[^a-z]", "", lp["expr"].lower())
            nr = _re.sub(r"[^a-z]", "", rp["expr"].lower())
            nl = nl[:-1] if nl.endswith("s") else nl
            nr = nr[:-1] if nr.endswith("s") else nr
            if nl and nl == nr:
                child = right
                parent = left
                child_col = lp["expr"] if child == left else rp["expr"]
                parent_col = lp["expr"] if parent == left else rp["expr"]
                parent_cube = _camel(parent).title() or "Cube"
                block = (
                    f"    {parent_cube}: {{ sql: "
                    f"`${{CUBE}}.\"{child_col}\" = "
                    f"`${{{parent_cube}}}.\"{parent_col}\"`, "
                    f"relationship: `belongsTo` }}"
                )
                edges.setdefault(child, {})[parent] = {"code": block}
    return edges


def transpile_dir(yaml_dir: str, out_dir: Optional[str] = None, overwrite: bool = False):
    models = load_osi_models(yaml_dir)
    join_map = _infer_identifier_joins(models)
    out_path = Path(out_dir) if out_dir else None
    results = []
    for ds in models:
        name = str(ds.get("name") or "cube")
        joins_code = "\n".join(v["code"] for v in join_map.get(name, {}).values())
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
                  "joins": {k: "belongsTo" for k in join_map.get(name, {})}}
        results.append({"table_name": name, "js_text": js, "report": report})

    if out_path is not None:
        (out_path / "_generation_report.json").write_text(
            json.dumps({r["table_name"]: r["report"] for r in results}, indent=1, ensure_ascii=False)
        )
    return results
