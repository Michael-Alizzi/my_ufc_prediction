#!/usr/bin/env python3
"""Statistical promotion test for shadow rules (C/E/F) vs rule A.

Replaces the raw "ahead on >=6 of 10 cards" sign-count from EXPERIMENTS.md
entry 9. That count isn't actually a statistical bar: under a coin-flip
null (zero real edge), P(>=6 of 10 wins) = 37.7% -- more than a third of
the time a shadow rule with no real edge clears it by chance. A plain sign
test fixes that but needs 9/10 (p=0.011) or arguably 8/10 (p=0.055) wins to
reach significance at n=10, which throws away all information about HOW
MUCH each card was won/lost by. The Wilcoxon signed-rank test uses both
sign and magnitude of the paired per-event net differences, giving more
power at the same sample size -- the right tool for "same cards, same
weeks, is one rule's return systematically bigger than the other's."

Revision recorded in EXPERIMENTS.md entry 9 (2026-08-20): this script is
the operational form of that revision. Run from a checkout of
weekly-predictions-log (ledger.md lives there).

Usage:
    python3 scripts/promotion_test.py [ledger.md] [--alpha 0.10] [--min-events 10]
"""
import argparse
import os
import sys

from scipy.stats import wilcoxon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_dashboard import parse_ledger  # noqa: E402


def paired_diffs(events, rule):
    """Real-$ net differences (rule - A) for events where both bet."""
    return [e["rules"][rule]["net"] - e["rules"]["A"]["net"]
            for e in events if rule in e["rules"] and "A" in e["rules"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger", nargs="?", default="ledger.md")
    ap.add_argument("--alpha", type=float, default=0.10,
                    help="one-sided significance threshold (default 0.10 -- "
                         "0.05 needs ~9/10 lopsided wins at this sample size, "
                         "see EXPERIMENTS.md entry 9)")
    ap.add_argument("--min-events", type=int, default=10,
                    help="paired events required before a verdict is issued "
                         "(default 10, per the original pre-registration)")
    args = ap.parse_args()

    events = parse_ledger(args.ledger)
    print(f"{len(events)} event(s) logged in {args.ledger}\n")

    for rule in "CEF":
        diffs = paired_diffs(events, rule)
        m = len(diffs)
        if m == 0:
            print(f"{rule}: no paired events logged yet")
            continue
        ahead = sum(1 for d in diffs if d > 0)
        cum = sum(diffs)
        nonzero = [d for d in diffs if d != 0]
        if len(nonzero) < 2:
            print(f"{rule}: {m} paired event(s), {ahead}/{m} ahead, "
                  f"cumulative edge {cum:+.2f} -- too few nonzero "
                  "differences for a signed-rank test yet")
            continue
        _, p = wilcoxon(diffs, alternative="greater", zero_method="wilcox")
        if m < args.min_events:
            verdict = f"insufficient events ({m}/{args.min_events} logged)"
        elif cum > 0 and p <= args.alpha:
            verdict = "PROMOTE"
        else:
            verdict = "A stands"
        print(f"{rule}: {m} paired events, {ahead}/{m} ahead, "
              f"cumulative real-$ edge {cum:+.2f}, "
              f"Wilcoxon one-sided p={p:.4f} (alpha={args.alpha}) -> {verdict}")


if __name__ == "__main__":
    main()
