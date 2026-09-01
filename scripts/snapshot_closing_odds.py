#!/usr/bin/env python3
"""Snapshot near-closing odds for the current card, for CLV grading.

Run shortly (~90 min) before the card's first fight — scheduled as a
one-shot by the Friday card-day Routine, which knows every fight's
commence_time from its own odds fetch. Reads the fighter pairs from
card.json, re-fetches current prices from The Odds API, and writes
closing_odds.json next to it; the Monday scoring job then computes each
bet's closing-line value (taken price / closing price - 1, same-book
Sportsbet basis so the vig cancels).

The Odds API drops an event once it starts, so this CANNOT run at scoring
time — fights already underway at snapshot time simply get no CLV (their
entry is absent and score_card shows "-").

Name matching is deliberately fuzzier than the card-day fetch, because
card.json carries data-normalized names ("Aoriqileng", "Ding Meng") while
the API uses its own forms ("Aori Qileng", "Meng Ding"): a pair matches if
the space-stripped names agree, or the token sets do.

Usage:  ODDS_API_KEY=... snapshot_closing_odds.py [--card card.json]
        [--out closing_odds.json]
"""
import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_card_odds import API, norm  # noqa: E402


def keys(a, b):
    """Both match keys for a fighter pair: space-stripped and token-set."""
    strip = frozenset((norm(a).replace(" ", ""), norm(b).replace(" ", "")))
    tokens = frozenset((frozenset(norm(a).split()), frozenset(norm(b).split())))
    return strip, tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", default="card.json")
    ap.add_argument("--out", default="closing_odds.json")
    args = ap.parse_args()

    key = os.environ.get("ODDS_API_KEY")
    if not key:
        sys.exit("Set ODDS_API_KEY")
    card = json.load(open(args.card))
    with urllib.request.urlopen(API.format(key=key), timeout=30) as r:
        events = json.load(r)

    by_strip, by_tokens = {}, {}
    for ev in events:
        h, a = ev.get("home_team", ""), ev.get("away_team", "")
        s, t = keys(h, a)
        by_strip[s] = by_tokens[t] = ev

    out = []
    for f in card:
        s, t = keys(f["fighter1"], f["fighter2"])
        ev = by_strip.get(s) or by_tokens.get(t)
        if not ev:
            print(f"no live odds (started/removed?): {f['fighter1']} vs {f['fighter2']}")
            continue
        h = ev["home_team"]
        sb1 = sb2 = None
        m1, m2 = [], []
        for bk in ev.get("bookmakers", []):
            for mkt in bk.get("markets", []):
                if mkt.get("key") != "h2h":
                    continue
                prices = {o["name"]: o["price"] for o in mkt["outcomes"]}
                p1, p2 = prices.get(ev["home_team"]), prices.get(ev["away_team"])
                if not (p1 and p2):
                    continue
                m1.append(p1)
                m2.append(p2)
                if bk.get("key") == "sportsbet":
                    sb1, sb2 = p1, p2
        if not m1:
            continue
        med = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
        c1, c2 = (sb1, sb2) if sb1 else (med(m1), med(m2))
        # orient API home/away onto the card's fighter1/fighter2
        hs = norm(h).replace(" ", "")
        f1s = norm(f["fighter1"]).replace(" ", "")
        home_is_f1 = (hs == f1s) or (frozenset(norm(h).split())
                                     == frozenset(norm(f["fighter1"]).split()))
        if not home_is_f1:
            c1, c2 = c2, c1
        out.append({"fighter1": f["fighter1"], "fighter2": f["fighter2"],
                    "close1": c1, "close2": c2,
                    "source": "sportsbet" if sb1 else f"au_median({len(m1)} books)"})
        print(f"{f['fighter1']} vs {f['fighter2']}: close {c1} / {c2}")

    json.dump(out, open(args.out, "w"), indent=1, ensure_ascii=False)
    print(f"wrote {args.out}: {len(out)}/{len(card)} fights")


if __name__ == "__main__":
    main()
