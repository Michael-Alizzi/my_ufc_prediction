#!/usr/bin/env python3
"""Fetch upcoming UFC card odds from The Odds API (au region) and write/update
card.json with the two-slot design (EXPERIMENTS.md entry 9 follow-up):

  odds1/odds2           staking slot -- Sportsbet's posted prices (the book
                        the user actually bets at); falls back to the AU
                        median where Sportsbet hasn't priced a fight yet.
  feat_odds1/feat_odds2 feature slot -- de-vigged median across all AU
                        books, re-expressed as decimal odds. This is the
                        model's market_prob input: a representative market
                        opinion, same KIND of number as the training data's
                        BFO-lineage closing figure.

Usage:
  ODDS_API_KEY=... fetch_card_odds.py [--card card.json] [--event-match TEXT]

Free-tier key from https://the-odds-api.com (500 requests/month; this uses 1
per run). Weight class / title_fight are NOT provided by the API -- new
skeleton entries get placeholders to fill by hand. If --card exists, only
odds fields are updated on fighter-name matches; unmatched API fights are
appended as skeletons.
"""
import argparse
import json
import os
import statistics
import sys
import unicodedata
import urllib.request

API = ("https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds"
       "?apiKey={key}&regions=au&markets=h2h&oddsFormat=decimal")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.lower().replace(".", "").strip()


def devig_median(prices_1, prices_2):
    """Median vig-free implied probability across books, back to decimal."""
    imps = [(1 / a) / (1 / a + 1 / b) for a, b in zip(prices_1, prices_2)]
    p = statistics.median(imps)
    return round(1 / p, 3), round(1 / (1 - p), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", default="card.json")
    ap.add_argument("--event-match", default="",
                    help="only fights whose event title contains this text")
    args = ap.parse_args()

    key = os.environ.get("ODDS_API_KEY")
    if not key:
        sys.exit("Set ODDS_API_KEY (free key: https://the-odds-api.com)")

    with urllib.request.urlopen(API.format(key=key), timeout=30) as r:
        events = json.load(r)

    fights = []
    for ev in events:
        if args.event_match and args.event_match.lower() not in ev.get(
                "sport_title", "").lower() + ev.get("home_team", "").lower():
            continue
        sb1 = sb2 = None
        all1, all2 = [], []
        f1, f2 = ev.get("home_team"), ev.get("away_team")
        for bk in ev.get("bookmakers", []):
            for mkt in bk.get("markets", []):
                if mkt.get("key") != "h2h":
                    continue
                prices = {norm(o["name"]): o["price"] for o in mkt["outcomes"]}
                p1, p2 = prices.get(norm(f1)), prices.get(norm(f2))
                if not (p1 and p2):
                    continue
                all1.append(p1)
                all2.append(p2)
                if bk.get("key") == "sportsbet":
                    sb1, sb2 = p1, p2
        if not all1:
            continue
        feat1, feat2 = devig_median(all1, all2)
        med1 = round(statistics.median(all1), 3)
        med2 = round(statistics.median(all2), 3)
        fights.append({
            "fighter1": f1, "fighter2": f2,
            "odds1": sb1 or med1, "odds2": sb2 or med2,
            "odds_source": "sportsbet" if sb1 else f"au_median({len(all1)} books)",
            "feat_odds1": feat1, "feat_odds2": feat2,
            "commence": ev.get("commence_time"),
        })

    if not fights:
        sys.exit("No MMA fights returned (check --event-match / API quota)")

    card = []
    if os.path.exists(args.card):
        card = json.load(open(args.card))
    by_name = {frozenset((norm(c["fighter1"]), norm(c["fighter2"]))): c
               for c in card}
    added = updated = 0
    for f in fights:
        k = frozenset((norm(f["fighter1"]), norm(f["fighter2"])))
        if k in by_name:
            by_name[k].update({x: f[x] for x in
                               ("odds1", "odds2", "feat_odds1", "feat_odds2",
                                "odds_source")})
            updated += 1
        else:
            card.append({"fighter1": f["fighter1"], "fighter2": f["fighter2"],
                         "weight_class": "?FILL?", "rounds": 3, **{
                             x: f[x] for x in ("odds1", "odds2", "feat_odds1",
                                               "feat_odds2", "odds_source",
                                               "commence")}})
            added += 1
    json.dump(card, open(args.card, "w"), indent=1)
    print(f"{args.card}: {updated} updated, {added} added "
          f"({sum(1 for f in fights if f['odds_source'] == 'sportsbet')} priced at sportsbet)")
    for f in fights:
        print(f"  {f['fighter1']} v {f['fighter2']}: stake @{f['odds1']}/{f['odds2']} "
              f"[{f['odds_source']}], feature @{f['feat_odds1']}/{f['feat_odds2']}")


if __name__ == "__main__":
    main()
