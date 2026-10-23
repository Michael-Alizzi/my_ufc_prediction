#!/usr/bin/env python3
"""Block-based promotion test for the staked betting rule (EXPERIMENTS.md
entry 11, superseding entry 9's open-ended Wilcoxon test).

The ledger's events are cut into consecutive, non-overlapping blocks of 10
cards. Each block is one experiment, judged exactly once, when its 10th
card is scored:

  * For every rule other than the one staked during the block, take its
    real-$ net minus the staked rule's net on each of the 10 cards.
  * One-sided exact sign-flip permutation test on the SUM of those dollar
    differences (all 2^10 sign patterns): how often would a rule with no
    real edge lead by at least this many dollars?
  * A challenger passes if it leads on dollars and p < 0.10 / 3 (three
    challengers tested per block, so ~10% chance of any false switch).
  * Several pass -> most cards ahead of the staked rule wins; still tied ->
    the bigger dollar lead.
  * The winner (if any) is staked from the next block on; the previous
    staked rule becomes a shadow and can win its place back.

Interim p-values are never computed for an unfinished block -- testing
every week and switching the first time p dips would inflate the false-
switch rate (peeking).

Run from a checkout of weekly-predictions-log (ledger.md lives there):
    python3 scripts/promotion_test.py [ledger.md]
"""
import argparse
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_dashboard import fetch_log_branch, git_show, parse_ledger, parse_ledger_lines  # noqa: E402

RULES = "ACEF"
BLOCK = 10
ALPHA = 0.10 / 3


def perm_p(diffs):
    """One-sided exact sign-flip permutation p-value for sum(diffs) > 0."""
    obs = sum(diffs)
    hits = sum(1 for signs in itertools.product((1, -1), repeat=len(diffs))
               if sum(s * d for s, d in zip(signs, diffs)) >= obs - 1e-9)
    return hits / 2 ** len(diffs)


def evaluate(events):
    """Walk the ledger block by block.

    Returns {"blocks": [completed block results], "current": {"n", "staked",
    "edges"}, "staked_by": {"date|event": rule staked on that card}}."""
    staked, blocks, staked_by = "A", [], {}
    for start in range(0, len(events), BLOCK):
        blk = events[start:start + BLOCK]
        for e in blk:
            missing = set(RULES) - set(e["rules"])
            if missing:
                raise ValueError(f"{e['date']} {e['event']}: no ledger row for rule(s) {sorted(missing)}")
            staked_by[e["date"] + "|" + e["event"]] = staked
        diffs = {r: [e["rules"][r]["net"] - e["rules"][staked]["net"] for e in blk]
                 for r in RULES if r != staked}
        if len(blk) < BLOCK:
            current = {"n": len(blk), "staked": staked,
                       "edges": {r: round(sum(d), 2) for r, d in diffs.items()}}
            return {"blocks": blocks, "current": current, "staked_by": staked_by}
        results = {r: {"edge": round(sum(d), 2), "ahead": sum(1 for x in d if x > 0),
                       "p": perm_p(d)} for r, d in diffs.items()}
        passing = [r for r, x in results.items() if x["edge"] > 0 and x["p"] < ALPHA]
        winner = max(passing, key=lambda r: (results[r]["ahead"], results[r]["edge"])) if passing else None
        blocks.append({"number": len(blocks) + 1, "first": blk[0]["date"], "last": blk[-1]["date"],
                       "staked": staked, "results": results, "winner": winner})
        if winner:
            staked = winner
    return {"blocks": blocks, "current": {"n": 0, "staked": staked, "edges": {}},
            "staked_by": staked_by}


def staked_rule_from_log():
    """The rule staked on the next card, from weekly-predictions-log's ledger."""
    fetch_log_branch()
    text = git_show("origin/weekly-predictions-log:ledger.md")
    if text is None:
        raise SystemExit("can't read ledger.md from origin/weekly-predictions-log")
    return evaluate(parse_ledger_lines(text.splitlines()))["current"]["staked"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger", nargs="?", default="ledger.md")
    args = ap.parse_args()

    trial = evaluate(parse_ledger(args.ledger))
    for b in trial["blocks"]:
        print(f"Experiment {b['number']} ({b['first']} to {b['last']}), rule {b['staked']} staked:")
        for r, x in b["results"].items():
            ok = "PASS" if x["edge"] > 0 and x["p"] < ALPHA else "fail"
            print(f"  {r}: {x['edge']:+.2f} vs {b['staked']}, {x['ahead']}/{BLOCK} cards ahead, "
                  f"permutation p={x['p']:.3f} (needs < {ALPHA:.3f}) -> {ok}")
        print(f"  -> {'switch to rule ' + b['winner'] if b['winner'] else b['staked'] + ' stays'}\n")
    c = trial["current"]
    print(f"Experiment {len(trial['blocks']) + 1} in progress: {c['n']}/{BLOCK} cards, "
          f"rule {c['staked']} staked"
          + ("".join(f"; {r} {v:+.2f}" for r, v in c["edges"].items()) if c["edges"] else "")
          + " (no p-values until the block completes)")


if __name__ == "__main__":
    main()
