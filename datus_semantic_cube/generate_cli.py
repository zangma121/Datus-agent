# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""CLI glue for ``datus generate-cube-models``: datasource-aware schema
providers + active-model LLM callable -> CubeModelGenerator."""

import json
from typing import Any, Callable, Dict, List

import httpx

from datus.utils.exceptions import DatusException, ErrorCode
from datus.utils.loggings import get_logger

logger = get_logger(__name__)


def _rows(result):
    """Normalize connector query results to list[dict]."""
    data = getattr(result, "sql_return", None)
    if isinstance(data, str):  # some connectors return JSON strings
        try:
            return json.loads(data)
        except Exception:  # noqa: BLE001
            return []
    return data or []


def make_providers(conn, db_type: str, schema_name: str = ""):
    """Build (list_tables, columns_for_table, sample_values) from a live
    connection using per-dialect metadata SQL."""
    t = db_type.lower()

    def _as_dicts(result):
        """Normalize ExecuteSQLResult to list[dict].

        sqlite's list format yields a header+CSV *string*; other dialects
        yield JSON-ready lists of dicts.
        """
        data = result.sql_return
        if isinstance(data, str):
            import csv as _csv
            import io as _io

            return [dict(r) for r in _csv.DictReader(_io.StringIO(data))]
        if isinstance(data, list) and data and not isinstance(data[0], dict):
            cols = getattr(result, "columns", None) or []
            if cols:
                return [dict(zip(cols, r)) for r in data]
        return data or []

    def q(sql: str):
        res = conn.execute_query(sql, result_format="list")
        return _as_dicts(res)

    def list_tables() -> List[str]:
        if t == "sqlite":
            rows = q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            return [r["name"] for r in rows]
        if t == "duckdb":
            rows = q(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema='{schema_name or 'main'}' AND table_type='BASE TABLE'"
            )
        else:  # postgres
            s = schema_name or "public"
            rows = q(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema='{s}' AND table_type='BASE TABLE'"
            )
        return [r.get("table_name") or r.get("TABLE_NAME") for r in rows]

    def columns(table: str) -> List[Dict[str, Any]]:
        if t == "sqlite":
            rows = q(f'PRAGMA table_info("{table}")')
            return [{"name": r["name"], "type": (r.get("type") or "").upper()} for r in rows]
        rows = q(
            "SELECT column_name, UPPER(data_type) AS type FROM information_schema.columns "
            f"WHERE table_name='{table}'"
            + (f" AND table_schema='{schema_name or 'main'}'" if t == "duckdb" else f" AND table_schema='{schema_name or 'public'}'")
        )
        return [
            {"name": r.get("column_name") or r.get("COLUMN_NAME"), "type": r.get("type")}
            for r in rows
        ]

    def sample_values(table: str, column: str, n: int = 5) -> List[Any]:
        rows = q(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT {n}')
        vals = []
        for r in rows:
            v = next(iter(r.values()), None)
            if v is not None and str(v).strip():
                vals.append(str(v)[:60])
        return vals

    return list_tables, columns, sample_values


def make_llm_fn(agent_config) -> Callable[[str, str], str]:
    """LLM closure over the agent's currently active model."""

    def llm(system: str, user: str) -> str:
        model_cfg = agent_config.active_model()
        resp = httpx.post(
            model_cfg.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {model_cfg.api_key}"},
            json={
                "model": model_cfg.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.0,
                "max_tokens": 2000,
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    return llm


def _finish(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Shared tail for both sources: print + log the summary, return it."""
    print(json.dumps(summary, indent=1))
    logger.info("generate-cube-models completed: %s", summary)
    return summary


def summary_exit_code(summary: Dict[str, Any]) -> int:
    """B4: scripted consumers get a non-zero exit when any model failed —
    lint_failed (or a defensive error/failed status); generated/skipped pass."""
    failed = {"lint_failed", "error", "failed"}
    return int(any(v.get("status") in failed for v in summary.values()))


def run_generate(args) -> Dict[str, Any]:
    """Entry point wired into datus/main.py dispatch."""
    # M8: --from-osi transpiles OSI YAML deterministically (no LLM, no DB).
    if getattr(args, "from_osi", None):
        from datus_semantic_cube.transpile import transpile_dir

        models = transpile_dir(args.from_osi, out_dir=args.out, overwrite=args.force)
        summary = {
            m["table_name"]: {"status": m["report"]["status"], "lint": m["report"]["lint"]["ok"]}
            for m in models
        }
        return _finish(summary)

    from datus.configuration.agent_config_loader import load_agent_config
    from datus.tools.db_tools.db_manager import DBManager
    from datus_semantic_cube.generate import CubeModelGenerator

    agent_config = load_agent_config(datasource=args.datasource)
    dm = DBManager(agent_config.services.datasources)
    conn = dm.get_conn(args.datasource)

    db_type = agent_config.services.datasources[args.datasource].type
    list_tables, columns, sample_values = make_providers(conn, db_type)

    wanted = [t.strip() for t in args.tables.split(",")] if getattr(args, "tables", None) else list_tables()

    generator = CubeModelGenerator(
        llm_fn=make_llm_fn(agent_config),
        table_names=wanted,
        column_provider=columns,
        sample_provider=sample_values,
        out_dir=args.out,
        overwrite=args.force,
        sample_rows=args.sample_rows,
    )
    models = generator.generate_models(out_dir=args.out)

    summary = {m.table_name: {"status": m.report["status"], "lint": m.report["lint"]["ok"]} for m in models}
    return _finish(summary)
