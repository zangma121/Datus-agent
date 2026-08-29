#!/usr/bin/env python
"""M5 experiment: BIRD questions -> Cube queries via LLM mapping.

For each BIRD dev question (california_schools subset), ask the LLM to emit
a Cube query (measures/dimensions/filters/order/limit) given the cube meta;
execute through our adapter; compare against gold SQL executed on the
sqlite source. This isolates the semantic-layer benefit: joins/metrics are
predefined, the LLM only picks them.

Usage: python benchmark/scripts/cube_bird_eval.py [--limit 30] [--json OUT]
"""

import argparse
import asyncio
import json
import os
import sqlite3
import time

from datus.utils.loggings import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You translate business questions into Cube.js queries for the california_schools dataset.

Available Cube members:
{meta}

Rules:
- Output ONLY a JSON object, no prose.
- Keys: "metrics" (list of measure names), "dimensions" (list or []), "where" (string or null), "order_by" (list like ["-Frpm.freeMealRateK12"] or []), "limit" (int or null).
- Member names MUST be copied verbatim from the list above. Never invent members.
- Where is ONE filter, exactly one of: "Cube.member = 'value'" | "Cube.member != 'value'" | "Cube.member IN ('a','b')" | "Cube.measure > 500" (also >=, <, <=).
- Rate questions use the *Rate/avg measures; totals use sums; school names/counties/districts are dimensions.
- Dimension-only queries ARE allowed (omit "metrics" or pass []) — use them for "list the X of schools" questions.
- Coded columns hold NUMERIC codes, never names: Charter=1/0, Virtual=F/P/N, DOC/SOC are numeric ownership/operation codes. District/county/school NAMES live in dedicated name dimensions (Frpm.districtName, Schools.district, ...). Never put a name into a code column filter.
- "Fresno County Office of Education" style values are DISTRICT names → use the districtName dimension of the matching cube.
- "Highest/lowest X" → order_by ["-Measure"] or ["Measure"] with limit 1 (or N for top N).
"""

BIRD_DB = os.path.expanduser("~/.datus/benchmark/bird/dev_20240627/dev_databases/california_schools/california_schools.sqlite")
BIRD_DEV = os.path.expanduser("~/.datus/benchmark/bird/dev_20240627/dev.json")


def load_meta(adapter) -> str:
    """Member listing WITH measure descriptions — descriptions are the
    semantic anchor; names alone made the LLM guess (Q0 picked the wrong
    member until descriptions were included)."""
    import collections

    metrics = asyncio.run(adapter.list_metrics(limit=10000))
    by_cube = collections.OrderedDict()
    dim_names = {m.name: m.dimensions for m in metrics}
    all_dims = {}
    for m in metrics:
        by_cube.setdefault(m.path[0] if m.path else "?", []).append(m)
        for d in m.dimensions or []:
            all_dims[d] = d.split(".")[0]

    # Dimensions via get_dimensions on first metric of each cube (cheap: cached /meta)
    lines = []
    for cube_name, ms in by_cube.items():
        lines.append(f"Cube {cube_name}:")
        for m in ms:
            desc = f" — {m.description}" if m.description else ""
            lines.append(f"  measure {m.name}{desc}")
    # dedupe dims across cubes
    shown = set()
    for cube_name, ms in by_cube.items():
        if not ms:
            continue
        try:
            dims = asyncio.run(adapter.get_dimensions(ms[0].name))
        except Exception:
            dims = []
        for d in dims:
            if d.name in shown:
                continue
            shown.add(d.name)
            dtxt = " (time)" if d.is_primary_time else ""
            # B2: dimension descriptions anchor filter-value selection the
            # same way measure descriptions anchor metric selection.
            ddesc = f" — {d.description}" if (getattr(d, "description", "") or "").strip() else ""
            lines.append(f"  dimension {d.name}{dtxt}{ddesc} [{cube_name}]")
    return "\n".join(lines)


def call_llm(system: str, user: str) -> str:
    import httpx

    resp = httpx.post(
        "https://ai.dev.gientechai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ.get('GIENAI_KEY', '123')}"},
        json={
            "model": os.environ.get("GIENAI_MODEL", "GS-Qwen3.6-35B-A3B"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.0,
            "max_tokens": 400,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def norm(v):
    if v is None:
        return ""
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return str(v).strip()


def compare(gold_rows, cube_rows):
    g = sorted(tuple(norm(c) for c in r) for r in gold_rows)
    c = sorted(tuple(norm(v) for v in (row.values())) for row in cube_rows)
    if len(g) != len(c):
        return False
    return all(set(x) == set(y) or list(x) == list(y) for x, y in zip(g, c))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    os.environ.setdefault("CUBEJS_API_SECRET", "datus-live-test-secret-0123456789abcdef")
    from datus_semantic_cube.adapter import CubeAdapter
    from datus_semantic_cube.config import CubeConfig

    adapter = CubeAdapter(CubeConfig(datasource="cube_live", api_url="http://localhost:4000/cubejs-api/v1"))
    meta = load_meta(adapter)
    system = SYSTEM_PROMPT.format(meta=meta)

    dev = json.load(open(BIRD_DEV))
    con = sqlite3.connect(BIRD_DB)

    results = []
    correct = 0
    attempted = 0
    t0 = time.time()
    for q in dev[: args.limit]:
        question, gold_sql, evidence = q["question"], q["SQL"], q.get("evidence") or ""
        try:
            raw = call_llm(system, f"Question: {question}\nEvidence: {evidence}")
            payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception as exc:
            results.append({"id": q["question_id"], "stage": "llm", "error": str(exc)[:120]})
            continue
        if payload.get("unanswerable"):
            results.append({"id": q["question_id"], "stage": "unanswerable"})
            continue
        try:
            r = asyncio.run(
                adapter.query_metrics(
                    metrics=payload.get("metrics") or [],
                    dimensions=payload.get("dimensions") or None,
                    where=payload.get("where"),
                    order_by=payload.get("order_by") or None,
                    limit=payload.get("limit"),
                )
            )
        except Exception as exc:
            results.append({"id": q["question_id"], "stage": "cube", "error": str(exc)[:120]})
            continue
        attempted += 1
        gold = con.execute(gold_sql).fetchall()
        ok = compare(gold, r.data)
        correct += ok
        results.append({"id": q["question_id"], "stage": "done", "correct": ok, "rows": len(r.data)})

    elapsed = time.time() - t0
    summary = {
        "total": args.limit,
        "attempted": attempted,
        "correct": correct,
        "accuracy_of_attempted": round(correct / attempted, 3) if attempted else None,
        "accuracy_of_total": round(correct / args.limit, 3),
        "seconds": round(elapsed, 1),
    }
    print(json.dumps(summary, indent=1))
    for row in results:
        if row.get("stage") != "done" or not row.get("correct"):
            print(" ", row)
    if args.json:
        json.dump({"summary": summary, "results": results}, open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()
