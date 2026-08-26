#!/usr/bin/env python
"""Compute BIRD accuracy for a datus benchmark run against gold SQL.

Compares each completed task's produced CSV against the gold SQL executed
on the same sqlite database (order-insensitive, floats rounded to 4dp).

Usage:
  python benchmark/scripts/bird_accuracy.py --run <run_id> [--benchmark bird_dev]

Example:
  python benchmark/scripts/bird_accuracy.py --run 20260826_140314
"""

import argparse
import csv
import json
import os
import sqlite3
import sys

DEFAULT_HOME = os.path.expanduser("~/.datus")
DEFAULT_BENCH = os.path.join(DEFAULT_HOME, "benchmark", "bird", "dev_20240627")


def norm(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return round(v, 4)
    return str(v).strip()


def rows_equal(gold_rows, pred_rows):
    g = sorted(tuple(norm(c) for c in r) for r in gold_rows)
    p = sorted(tuple(str(c).strip() for c in r) for r in pred_rows)
    return len(g) == len(p) and all(x == y for x, y in zip(g, p))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="run_id under ~/.datus/save/bird_sqlite/")
    ap.add_argument("--bench-dir", default=DEFAULT_BENCH, help="BIRD dev dataset directory")
    ap.add_argument("--datasource", default="bird_sqlite")
    ap.add_argument("--limit", type=int, default=None, help="only consider task ids < limit")
    args = ap.parse_args()

    run_dir = os.path.join(DEFAULT_HOME, "save", args.datasource, args.run)
    if not os.path.isdir(run_dir):
        sys.exit(f"run dir not found: {run_dir}")

    dev = json.load(open(os.path.join(args.bench_dir, "dev.json")))
    db_base = os.path.join(args.bench_dir, "dev_databases")

    task_ids = sorted(
        int(f.split(".")[0]) for f in os.listdir(run_dir) if f.endswith(".csv") and f.split(".")[0].isdigit()
    )
    if args.limit:
        task_ids = [t for t in task_ids if t < args.limit]

    correct, completed = 0, 0
    wrong = []
    for t in task_ids:
        q = dev[t]
        completed += 1
        try:
            con = sqlite3.connect(os.path.join(db_base, q["db_id"], f"{q['db_id']}.sqlite"))
            gold = con.execute(q["SQL"]).fetchall()
            con.close()
        except Exception as e:
            wrong.append((t, f"gold-error: {e}"))
            continue
        with open(os.path.join(run_dir, f"{t}.csv")) as f:
            pred = [row for row in csv.reader(f)][1:]  # skip header
        if rows_equal(gold, pred):
            correct += 1
        else:
            wrong.append((t, q["question"][:60]))

    print(f"run:      {args.run}")
    print(f"completed with result CSV: {completed}")
    print(f"correct:  {correct}/{completed} = {correct / completed * 100:.1f}%" if completed else "no completed tasks")
    if wrong:
        print("wrong tasks:")
        for t, why in wrong:
            print(f"  {t}: {why}")


if __name__ == "__main__":
    main()
