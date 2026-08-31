# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Datus-native Cube model generation (M7).

Turns a datasource's schema + sampled values into complete, lint-checked
cube .js model files: heuristic dimension/measure/PK classification, LLM
authored bilingual descriptions and aliases, LLM/heuristic cross-table
join inference, and a generation report that records every failure or
confidence note.

LLM and schema access are injected callables, so unit tests run without a
database or network. Production wiring maps them onto the datasource's
connector (see cli subcommand in datus/main.py).
"""

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from datus.utils.loggings import get_logger
from datus_semantic_cube.naming import JS_IDENT_RE as _JS_IDENT
from datus_semantic_cube.naming import camel as _camel
from datus_semantic_cube.naming import normalize_join_name as _normalize_join_name

logger = get_logger(__name__)

# Identifier-like suffixes that hint at primary keys.
_PK_HINT_RE = re.compile(r"(^|_)(id|code|key|cds)$", re.IGNORECASE)

_NUMERIC_PREFIXES = (
    "int", "bigint", "smallint", "tinyint", "real", "float",
    "double", "decimal", "numeric", "number",
)


def _is_numeric(dtype: str) -> bool:
    """Prefix match so parameterized forms (numeric(10,2)) count too."""
    d = (dtype or "").lower().strip()
    return d.startswith(_NUMERIC_PREFIXES)

_SYSTEM_DESC = """You enrich BI semantic-model members. For EACH column return its
bilingual description and search aliases.
Output ONLY JSON: {"columns": {"<column>": {"description": "<EN sentence. 中文一句话>",
"aliases": ["...", "..."]}}}
Rules: coded/enumerated columns MUST explain what values mean; include
English and 中文 aliases likely used in business questions."""




def render_aliases_meta(aliases) -> str:
    """Render aliases as structured Cube member meta (B1): ``meta: { aliases:
    [`a`, `b`] }`` — /meta echoes member meta, letting the knowledge base
    sync aliases without parsing them out of the description text. Empty
    input renders as empty string (no meta member)."""
    if not aliases:
        return ""
    items = ", ".join("`" + str(a).replace("`", "'") + "`" for a in aliases if str(a).strip())
    return f"meta: {{ aliases: [{items}] }}" if items else ""


def lint_model_text(js_text: str):
    """Structural lint: balanced braces/backticks + required markers."""
    issues: List[str] = []
    stack_balance = js_text.count("{") - js_text.count("}")
    if stack_balance != 0:
        issues.append(f"unbalanced braces ({stack_balance:+d})")
    if js_text.count("`") % 2:
        issues.append("unbalanced backticks")
    if "cube(" not in js_text:
        issues.append("missing cube( declaration")
    if "sql:" not in js_text:
        issues.append("member missing sql:")
    for mkey in re.finditer(r"([A-Za-z0-9_$]*):\s*\{\s*sql:", js_text):
        if not _JS_IDENT.match(mkey.group(1)):
            issues.append(f"illegal JS member identifier: {mkey.group(1)!r}")
    if 'description: ""' in js_text:
        issues.append('empty description strings are rejected by Cube')
    member_names = re.findall(r"^\s+([A-Za-z0-9_$]+):\s*\{", js_text, re.M)
    seen, dups = set(), set()
    for nme in member_names:
        (dups if nme in seen else seen).add(nme)
    if dups:
        issues.append(f"duplicate member names across dimensions/measures: {sorted(dups)}")
    return (not issues), issues


@dataclasses.dataclass
class GeneratedModel:
    table_name: str
    cube_name: str
    js_text: str
    primary_key: Optional[str]
    measures: List[str]
    report: Dict[str, Any]


class CubeModelGenerator:
    """Generate cube .js models from schema info + samples via LLM."""

    def __init__(
        self,
        llm_fn: Callable[[str, str], str],
        table_names: List[str],
        column_provider: Callable[[str], List[dict]],
        sample_provider: Callable[[str, str, int], list],
        out_dir: Optional[str] = None,
        overwrite: bool = False,
        sample_rows: int = 5,
        join_unverified_policy: str = "open",
    ):
        if join_unverified_policy not in ("open", "strict"):
            raise ValueError(
                f"join_unverified_policy must be 'open' or 'strict', got {join_unverified_policy!r}"
            )
        self.llm_fn = llm_fn
        self.table_names = list(table_names)
        self.column_provider = column_provider
        self.sample_provider = sample_provider
        self.out_dir = Path(out_dir) if out_dir else None
        self.overwrite = overwrite
        self.sample_rows = sample_rows
        # B3: what happens to heuristic join candidates the LLM did not
        # confirm. 'open' keeps them marked heuristic-unverified; 'strict'
        # drops them (permission-sensitive tenants).
        self.join_unverified_policy = join_unverified_policy
        self._last_joins_dropped: Dict[str, int] = {"rejected": 0, "unverified": 0}

    # ── classification ───────────────────────────────────────────────

    def _pick_primary_key(self, columns: List[dict]):
        """Always yields a PK column + confidence: cubes that define joins
        MUST declare one (Cube compiler constraint), even without uniqueness
        metadata."""
        idish = [c["name"] for c in columns
                 if c.get("unique") and _PK_HINT_RE.search(c["name"])]
        if idish:
            return idish[0], "high"
        hinted = [c["name"] for c in columns if _PK_HINT_RE.search(c["name"])]
        if hinted:
            return hinted[0], "low (no uniqueness metadata)"
        non_numeric = next((c["name"] for c in columns if not _is_numeric(c["type"])), columns[0]["name"])
        return non_numeric, "low (fallback first string column)"

    # ── LLM descriptions ─────────────────────────────────────────────

    def _describe_columns(self, table: str, columns: List[dict]) -> Dict[str, dict]:
        listing = []
        samples_by_col = {}
        for c in columns:
            samples = self.sample_provider(table, c["name"], self.sample_rows)
            samples_by_col[c["name"]] = samples
            listing.append(
                f"- {c['name']} ({c['type']}): samples={json.dumps(samples, ensure_ascii=False)}"
            )
        user = f"Table: {table}\nColumns:\n" + "\n".join(listing)

        last_err = None
        for _attempt in range(2):  # retry once on malformed output
            try:
                raw = self.llm_fn(_SYSTEM_DESC, user)
                payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
                cols_out = payload.get("columns") or {}
                return {
                    c["name"]: {
                        "description": (cols_out.get(c["name"]) or {}).get("description", ""),
                        "aliases": (cols_out.get(c["name"]) or {}).get("aliases", []),
                    }
                    for c in columns
                }
            except Exception as exc:  # noqa: BLE001 - record & retry then degrade
                last_err = str(exc)[:120]

        logger.warning("Description enrichment failed for table %s: %s", table, last_err)
        return {c["name"]: {"description": "", "aliases": [], "_failed": last_err} for c in columns}

    # ── rendering ────────────────────────────────────────────────────

    def _render(self, table: str, columns: List[dict], pk: Optional[str], descriptions: Dict[str, dict], joins_code: str) -> str:
        dims = []
        measures = ["    " + _camel(table) + "Count: { sql: `1`, type: `count` },"]
        for c in columns:
            name = c["name"]
            safe_sql_col = '"' + name.replace('"', '""') + '"'
            dtype = "number" if _is_numeric(c["type"]) else "string"
            desc = descriptions.get(name, {}).get("description", "")
            # Cube rejects empty description strings; omit the field instead.
            desc_js = json.dumps(desc, ensure_ascii=True) if desc else None
            entry_parts = [f'sql: `{safe_sql_col}`', f"type: `{dtype}`"]
            if name == pk:
                entry_parts.append("primaryKey: true")
            if desc_js is not None:
                entry_parts.append(f"description: {desc_js}")
            dim_meta = render_aliases_meta(descriptions.get(name, {}).get("aliases"))
            if dim_meta:
                entry_parts.append(dim_meta)
            dims.append(f"    {_camel(name)}: {{ {', '.join(entry_parts) } }},")

            if _is_numeric(c["type"]) and name != pk:
                # NOTE: Cube adds its own aggregate for type:`sum` — the
                # member sql must stay a bare column expression or every
                # query compiles to illegal nested aggregates.
                m_sql = f'CAST({safe_sql_col} AS DOUBLE PRECISION)'
                m_name = _camel(name) + "Total"  # avoid clashing with the dimension member
                m_desc = json.dumps(descriptions.get(name, {}).get("description", ""), ensure_ascii=True) if desc else None
                desc_part = f", description: {m_desc}" if m_desc is not None else ""
                m_meta = render_aliases_meta(descriptions.get(name, {}).get("aliases"))
                meta_part = f", {m_meta}" if m_meta else ""
                measures.append(
                    f"    {m_name}: {{ sql: `{m_sql}`, type: `sum`{desc_part}{meta_part} }},"
                )

        join_block = f"\n  joins: {{\n{joins_code}\n  }}," if joins_code.strip() else ""
        lines = [
            f"cube(`{self._cube_name(table)}`, {{",
            f"  sql: `SELECT * FROM {table}`," + join_block,
            "  measures: {",
            *measures,
            "  },",
            "  dimensions: {",
            *dims,
            "  },",
            "});",
        ]
        return "\n".join(lines)

    @staticmethod
    def _cube_name(table: str) -> str:
        core = re.sub(r"[^A-Za-z0-9]", "", table.title()) or table
        return core

    def build_model(self, table: str, joins_code: str = "") -> GeneratedModel:
        columns = self.column_provider(table)
        pk, pk_confidence = self._pick_primary_key(columns)
        described = self._describe_columns(table, columns)
        failed = sum(1 for d in described.values() if d.get("_failed"))
        js = self._render(table, columns, pk, described, joins_code)
        ok, issues = lint_model_text(js)
        measures = [_camel(c["name"]) for c in columns if _is_numeric(c["type"]) and c["name"] != pk]
        measures.insert(0, _camel(table) + "Count")
        report = {
            "status": "built",
            "descriptions_failed": failed,
            "primary_key": pk,
            "pk_confidence": pk_confidence,
            "lint": {"ok": ok, "issues": issues},
            "joins": {},
        }
        return GeneratedModel(table_name=table, cube_name=self._cube_name(table), js_text=js,
                              primary_key=pk, measures=measures, report=report)

    # ── join inference ───────────────────────────────────────────────

    def _infer_joins(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Heuristic key matches -> LLM confirmation -> direction resolution.

        Direction: the table whose matched column is its own primary-key
        candidate is the parent (one-side); the other table receives a
        ``belongsTo`` edge joining its OWN column to the parent's column.
        Falls back to alphabetical-first-as-parent (low confidence) when
        neither matched column is a PK candidate.
        """
        cache = {t: self.column_provider(t) for t in self.table_names}
        norm = lambda s: _normalize_join_name(s)  # noqa: E731
        pks = {t: self._pick_primary_key(cache[t])[0] for t in self.table_names}

        candidates: List[Tuple[str, str, str, str]] = []
        self._last_joins_dropped = {"rejected": 0, "unverified": 0}
        names = sorted(self.table_names)
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                lmap = {norm(c["name"]): c for c in cache[left] if c.get("name")}
                rmap = {norm(c["name"]): c for c in cache[right] if c.get("name")}
                best: Optional[Tuple[str, str]] = None
                for key, lc in lmap.items():
                    rc = rmap.get(key)
                    if rc and key and _is_numeric(lc["type"]) == _is_numeric(rc["type"]):
                        best = (lc["name"], rc["name"])
                        break
                if best:
                    candidates.append((left, right, best[0], best[1]))

        confirmed: List[Tuple[str, str, str, str, str]] = []
        if candidates:
            listing = "\n".join(
                f"- pair {i}: {l}.{lc} <-> {r}.{rc}"
                for i, (l, r, lc, rc) in enumerate(candidates)
            )
            verify_prompt = (
                "Each proposed BI join pairs a column from two tables. Mark each as "
                "plausible primary-key/foreign-key pairing or not.\n"
                f"{listing}\n"
                'Output ONLY JSON array: [{"pair": 0, "plausible": true}, ...]'
            )
            try:
                raw = self.llm_fn("You verify BI semantic-layer join mappings.", verify_prompt)
                arr = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
                verdicts = {
                    int(item.get("pair")): bool(item.get("plausible"))
                    for item in arr if isinstance(item, dict)
                }
            except Exception as exc:  # noqa: BLE001 - degrade to heuristics
                logger.warning("Join LLM verification failed; heuristic edges kept: %s", exc)
                verdicts = {}
            dropped = {"rejected": 0, "unverified": 0}
            for idx, cand in enumerate(candidates):
                l, r, lc, rc = cand
                if idx in verdicts:
                    if not verdicts[idx]:
                        # LLM explicitly rejected the pairing — dropped under
                        # every policy.
                        dropped["rejected"] += 1
                        continue
                    confirmed.append((l, r, lc, rc, "llm"))
                elif self.join_unverified_policy == "strict":
                    dropped["unverified"] += 1
                else:
                    confirmed.append((l, r, lc, rc, "heuristic-unverified"))
            self._last_joins_dropped = dropped

        edges: Dict[str, Dict[str, Dict[str, Any]]] = {}
        pks = pks  # closure reference
        for left, right, lcol, rcol, verified_by in confirmed:
            l_parent = pks.get(left) == lcol
            r_parent = pks.get(right) == rcol
            parent_table = left if l_parent else (right if r_parent else sorted([left, right])[0])
            child_table = right if parent_table == left else left
            parent_col = lcol if parent_table == left else rcol
            child_col = rcol if parent_table == left else lcol

            block = (
                f"    {self._cube_name(parent_table)}: {{ sql: "
                f"`${{CUBE}}.\"{child_col}\" = ${{{self._cube_name(parent_table)}}}.\"{parent_col}\"`, "
                f"relationship: `belongsTo` }}"
            )
            edges.setdefault(child_table, {})[parent_table] = {
                "code": block,
                "on": f"{left}.{lcol} = {right}.{rcol}",
                "verified_by": verified_by,
                "relationship": "belongsTo",
            }
        return edges

    # ── orchestration ────────────────────────────────────────────────

    def generate_models(self, out_dir: Optional[str] = None):
        out_dir_path = Path(out_dir) if out_dir else self.out_dir
        join_map = self._infer_joins()
        models: List[GeneratedModel] = []

        for table in self.table_names:
            joins_code = "\n".join(v["code"] for v in join_map.get(table, {}).values())
            model = self.build_model(table, joins_code=joins_code)
            model.report["joins"] = {
                w: {"relationship": v["relationship"],
                    "verified_by": v["verified_by"],
                    "on": v["on"]}
                for w, v in join_map.get(table, {}).items()
            }
            model.report["joins_dropped"] = dict(self._last_joins_dropped)
            status = "generated"
            target = out_dir_path / f"{model.table_name}.js"
            if out_dir_path is not None:
                if target.exists() and not self.overwrite:
                    status = "skipped"
                else:
                    out_dir_path.mkdir(parents=True, exist_ok=True)
                    target.write_text(model.js_text)
            model.report["status"] = status
            if model.report["lint"]["issues"]:
                model.report["status"] = "lint_failed"
            models.append(model)

        if out_dir_path is not None:
            (out_dir_path / "_generation_report.json").write_text(
                json.dumps({m.table_name: m.report for m in models}, indent=1, ensure_ascii=False)
            )
        return models
