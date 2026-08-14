#!/usr/bin/env python3
"""Build odds_train.csv (gitignored) -- the market-prob training data.

Two sources, merged (EXPERIMENTS.md entry 5 phase 2):
1. The mma-ai dump, downloaded straight from its original PUBLIC host
   (HuggingFace) at build time. The repo never redistributes it (no license
   upstream -- see the market-comparison rule in EXPERIMENTS.md): the file
   is cached under ~/.cache and the derived odds_train.csv is gitignored.
   Extracted with `pg_restore --data-only -f -` text emission -- no
   Postgres server needed. Coverage: 2007 -> Feb 2026.
2. collected_odds.csv on the weekly-predictions-log branch: our own
   per-card odds, appended by scripts/score_card.py each event from Aug
   2026 onward. Read via `git show` -- no branch switching.

Usage (from the repo root; needs pg_restore on PATH + huggingface.co
reachable):
    python3 scripts/fetch_training_odds.py [--dump PATH]
"""
import argparse
import io
import os
import subprocess
import sys
import urllib.request

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, ".")
from odds_backtest import join_odds, norm  # noqa: E402  (same matching logic as the backtest)

DUMP_URL = ("https://huggingface.co/datasets/DanMcInerney/mma-ai/resolve/"
            "main/dumps/mma-ai.postgres-custom")
DUMP_CACHE = os.path.expanduser("~/.cache/mma-ai/mma-ai.postgres-custom")
COLLECTED_REF = "origin/weekly-predictions-log:collected_odds.csv"


def parse_copy_tables(text, wanted):
    """Parse `COPY schema.table (cols) FROM stdin;` blocks out of pg_restore's
    text emission into DataFrames. Tab-separated rows, \\N = NULL."""
    tables = {}
    lines = iter(text.splitlines())
    for line in lines:
        if not line.startswith("COPY "):
            continue
        head = line[len("COPY "):]
        table = head.split(" (")[0].split(".")[-1]
        if table not in wanted:
            continue
        cols = head[head.index("(") + 1:head.index(")")].split(", ")
        rows = []
        for row in lines:
            if row == "\\.":
                break
            rows.append([None if v == "\\N" else v for v in row.split("\t")])
        tables[table] = pd.DataFrame(rows, columns=cols)
    missing = wanted - set(tables)
    if missing:
        raise SystemExit(f"tables not found in dump emission: {missing} "
                         "(schema drift? inspect with pg_restore -l)")
    return tables


def dump_odds(dump_path):
    """fighter-date closing quotes from the dump, matching load_odds' shape."""
    out = subprocess.run(
        ["pg_restore", "--data-only", "-t", "odds", "-t", "fighter_mapping",
         "-t", "event_mapping", "-f", "-", dump_path],
        capture_output=True, text=True, check=True)
    t = parse_copy_tables(out.stdout, {"odds", "fighter_mapping", "event_mapping"})
    odds = (t["odds"].merge(t["fighter_mapping"], on="fighter_id")
                     .merge(t["event_mapping"], on="event_id"))
    odds["closing_odds"] = pd.to_numeric(odds["closing_odds"], errors="coerce")
    odds = odds[odds["closing_odds"] > 1.0].dropna(subset=["closing_odds"])
    odds["name"] = odds["fighter_name"].map(norm)
    odds["date"] = pd.to_datetime(odds["event_date"])
    return odds.groupby(["name", "date"], as_index=False)["closing_odds"].median()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=DUMP_CACHE,
                    help="mma-ai dump path (downloaded from HuggingFace if absent)")
    ap.add_argument("--out", default="odds_train.csv")
    args = ap.parse_args()

    if not os.path.exists(args.dump):
        os.makedirs(os.path.dirname(args.dump), exist_ok=True)
        print(f"downloading dump from {DUMP_URL} (~2.5GB, once per container)...")
        urllib.request.urlretrieve(DUMP_URL, args.dump)
    odds = dump_odds(args.dump)
    print(f"dump: {len(odds)} fighter-date closing quotes")

    fights = pd.read_parquet("fighter_history.parquet")[
        ["r_fighter", "b_fighter", "date_d"]]
    out = join_odds(fights, odds)
    print(f"dump join: {len(out)}/{len(fights)} fights with odds")

    # Phase-2 feed: our own collected card odds (fight-keyed already).
    got = subprocess.run(["git", "show", COLLECTED_REF],
                         capture_output=True, text=True)
    if got.returncode == 0:
        ours = pd.read_csv(io.StringIO(got.stdout), parse_dates=["date_d"])
        new = ours.merge(out[["r_fighter", "b_fighter", "date_d"]],
                         on=["r_fighter", "b_fighter", "date_d"],
                         how="left", indicator=True)
        new = new[new["_merge"] == "left_only"].drop(columns="_merge")
        out = pd.concat([out, new[out.columns]], ignore_index=True)
        print(f"collected_odds.csv: +{len(new)} fights (total {len(out)})")
    else:
        print("no collected_odds.csv on the log branch yet -- dump only")

    out.sort_values("date_d").to_csv(args.out, index=False)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
