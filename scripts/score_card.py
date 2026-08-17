#!/usr/bin/env python3
"""Grade a logged card and append the running ledger + collected-odds feed.

Run from a checkout of the weekly-predictions-log branch (card.json,
predictions_output.md, ledger.md, collected_odds.csv all live there). The
Sunday Routine session fetches the results itself (web) and passes them in;
this script only does the deterministic part: recompute every rule's stakes
from card.json (same code path that produced the logged table), grade them,
append one ledger row per rule, and append the card's odds to the phase-2
training feed.

Usage:
    python3 scripts/score_card.py results.json --event-title "UFC 330" \
        --event-date 2026-08-15 [--bankroll 50]

results.json: {"winners": ["fighter name", ...],
               "voids": [["fighter1", "fighter2"], ...]}   # cancelled/changed
Winners are matched case-insensitively. A staked fight must appear in
winners (either corner) or voids, else this exits asking for it -- silent
holes would corrupt the 10-event promotion record (EXPERIMENTS.md entry 9).
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, ".")
from predict import load_artifacts, load_history  # noqa: E402
from send_weekly_predictions import make_predictions  # noqa: E402

LEDGER = "ledger.md"
COLLECTED = "collected_odds.csv"
LEDGER_HEADER = (
    "# Weekly betting ledger (rule A staked; C/E shadow per entry 9, F per entry 10)\n\n"
    "| Date | Event | Rule | Staked | Returned | Net | Bets won/placed/void | Flat $1 net |\n"
    "|---|---|---|---|---|---|---|---|\n"
)


def grade(rule_bets, winners, voids):
    """rule_bets: [(fighter1, fighter2, bet_on, odds, stake), ...]

    Returns real staked/returned/won/void (actual $ risked) AND flat_net --
    profit at a flat $1 per bet, ignoring stake size. The two diverge
    because rules concentrate differently: a rule that puts its whole
    bankroll on one bet (e.g. C most weeks) swings by a lot more real
    dollars than a rule spreading across several -- comparing rules on
    real $ overstates whichever one happens to concentrate more.  Flat
    net is the same convention scripts/betting_rule_compare.py and the
    dashboard's History replay already use for exactly this reason, kept
    consistent here so the live comparison isn't skewed by stake sizing."""
    staked = returned = won = void = 0
    flat_net = 0.0
    for f1, f2, bet_on, odds, stake in rule_bets:
        pair = {f1.lower(), f2.lower()}
        if any(pair == {a.lower(), b.lower()} for a, b in voids):
            void += 1
            continue  # stake returned, not risked
        winner = next((w for w in winners if w.lower() in pair), None)
        if winner is None:
            raise SystemExit(f"no result for staked fight {f1} vs {f2} -- "
                             "add it to winners or voids")
        staked += stake
        if winner.lower() == bet_on.lower():
            won += 1
            returned += stake * odds
            flat_net += odds - 1
        else:
            flat_net -= 1
    return staked, returned, won, void, flat_net


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--event-title", required=True)
    ap.add_argument("--event-date", required=True)
    ap.add_argument("--bankroll", type=int, default=50)
    ap.add_argument("--event-country", default=None)
    args = ap.parse_args()

    res = json.load(open(args.results))
    winners, voids = res["winners"], res.get("voids", [])
    fights = json.load(open("card.json"))

    artifacts, history = load_artifacts(), load_history()
    preds = make_predictions(fights, history, artifacts,
                             event_country=args.event_country,
                             bankroll=args.bankroll)

    rules = {"A": [], "C": [], "E": [], "F": []}
    for p, f in zip(preds, fights):
        if p.get("stake_amt"):
            rules["A"].append((p["fighter1"], p["fighter2"], p["bet_on"],
                               p["bet_odds"], p["stake_amt"]))
        # shadow strings like "C: $50 on Donte Johnson (@1.40)"
        for part in (p.get("shadow") or "").split(" / "):
            if part.startswith(("C:", "E:", "F:")):
                rule = part[0]
                amt = int(part.split("$")[1].split(" ")[0])
                name = part.split(" on ")[1].split(" (@")[0]
                odds = float(part.split("(@")[1].rstrip(")"))
                rules[rule].append((p["fighter1"], p["fighter2"], name, odds, amt))

    if not os.path.exists(LEDGER):
        open(LEDGER, "w").write(LEDGER_HEADER)
    with open(LEDGER, "a") as fh:
        for rule, bets in rules.items():
            staked, ret, won, void, flat_net = grade(bets, winners, voids)
            fh.write(f"| {args.event_date} | {args.event_title} | {rule} "
                     f"| ${staked} | ${ret:.2f} | {ret - staked:+.2f} "
                     f"| {won}/{len(bets) - void}/{void} | {flat_net:+.2f} |\n")
            print(f"rule {rule}: staked ${staked}, returned ${ret:.2f} "
                  f"({won}/{len(bets) - void} won, {void} void, flat net {flat_net:+.2f})")

    # Phase-2 training feed: every fight's odds (feature slot preferred),
    # keyed the way fighter_history/odds_train are.
    rows = [{"r_fighter": f["fighter1"].lower().strip(),
             "b_fighter": f["fighter2"].lower().strip(),
             "date_d": args.event_date,
             "odds_r": f.get("feat_odds1", f.get("odds1")),
             "odds_b": f.get("feat_odds2", f.get("odds2"))}
            for f in fights if f.get("odds1") and f.get("odds2")]
    feed = pd.DataFrame(rows)
    header = not os.path.exists(COLLECTED)
    feed.to_csv(COLLECTED, mode="a", header=header, index=False)
    print(f"appended {len(feed)} fights to {COLLECTED}")


if __name__ == "__main__":
    main()
