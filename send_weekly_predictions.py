#!/usr/bin/env python3
"""Predict a UFC fight card and write a markdown results table.

Usage:
  python send_weekly_predictions.py --fights-json card.json --event-title "UFC ..." \
      [--event-country USA]

card.json is a list of {"fighter1", "fighter2", "weight_class"} dicts, each
optionally with title_fight (bool), rounds (3 or 5, defaults to 3), and
odds1/odds2 (decimal bookmaker odds for fighter1/fighter2, used to size bets).
--event-country is the card's host country (feeds the home-crowd features);
omit it if unknown and they fall back to NaN.

Prints the markdown table and writes it to predictions_output.md. The weekly
Routine commits that file to the weekly-predictions-log branch — that push is
the delivery mechanism; there is no email path.
"""
import argparse
import json
import logging
import os
import shutil
from datetime import datetime

import pandas as pd

from predict import kelly_edge, load_artifacts, load_history, predict_winner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def make_predictions(fights, history, artifacts, event_country=None):
    """Predict each fight and size bets.

    Bet sizing: the whole $100 bankroll is split across every side of every
    fight where the model's probability beats the odds' implied probability,
    proportionally to Kelly fraction. The value side can be the fighter the
    model predicts to LOSE (a narrow pick priced by the market as a lock).
    "$0 (no value)" = odds given but neither side is mispriced enough;
    "-" = no odds provided or the fight couldn't be predicted.
    """
    predictions = []
    known = set(pd.concat([history["r_fighter"], history["b_fighter"]]).unique())

    for fight in fights:
        try:
            fighter1 = fight["fighter1"].lower().strip()
            fighter2 = fight["fighter2"].lower().strip()
            weight_class = fight.get("weight_class", "Middleweight")
            title_fight = bool(fight.get("title_fight", False))
            rounds = 5 if title_fight else int(fight.get("rounds", 3))

            missing = [f for f in (fighter1, fighter2) if f not in known]
            if missing:
                logger.warning(f"Skipping {fighter1} vs {fighter2}: no history for {missing}")
                predictions.append({
                    "fighter1": fight["fighter1"], "fighter2": fight["fighter2"],
                    "weight_class": weight_class, "prediction": "no data",
                    "confidence": "-",
                })
                continue

            winner, proba = predict_winner(
                fighter1, fighter2, weight_class,
                title_fight=title_fight,
                total_round_number=rounds,
                history=history,
                artifacts=artifacts,
                event_country=event_country,
            )

            confidence = proba if winner == fighter1 else 1 - proba

            # Find the value side, if any: at most one side of a fight can
            # have model probability above the odds' implied probability.
            bet_on, bet_odds, kelly = None, None, 0.0
            has_odds = False
            for name, p, o in ((fight["fighter1"], proba, fight.get("odds1")),
                               (fight["fighter2"], 1 - proba, fight.get("odds2"))):
                if not o:
                    continue
                has_odds = True
                k = kelly_edge(p, float(o))
                if k > 0:
                    bet_on, bet_odds, kelly = name, float(o), k

            predictions.append({
                "fighter1": fight["fighter1"],
                "fighter2": fight["fighter2"],
                "weight_class": weight_class,
                "prediction": winner.title(),
                "confidence": f"{confidence:.1%}",
                "stake": "$0 (no value)" if has_odds else "-",
                "bet_on": bet_on,
                "bet_odds": bet_odds,
                "kelly": kelly,
            })
        except Exception as e:
            logger.error(f"Prediction failed for {fight['fighter1']} vs {fight['fighter2']}: {e}")
            predictions.append({
                "fighter1": fight["fighter1"], "fighter2": fight["fighter2"],
                "weight_class": fight.get("weight_class", "?"),
                "prediction": "error", "confidence": "-",
            })
            continue

    # Split the $100 bankroll across all value bets, proportional to Kelly.
    value = [p for p in predictions if p.get("kelly", 0) > 0]
    if value:
        total = sum(p["kelly"] for p in value)
        for p in value:
            p["stake_amt"] = round(100 * p["kelly"] / total)
        max(value, key=lambda p: p["kelly"])["stake_amt"] += 100 - sum(
            p["stake_amt"] for p in value
        )
        for p in value:
            payout = round(p["stake_amt"] * p["bet_odds"])
            p["stake"] = (
                f"${p['stake_amt']} on {p['bet_on'].title()} "
                f"(@{p['bet_odds']:.2f}, returns ~${payout})"
            )

    return predictions


def format_predictions_markdown(event_title, predictions):
    lines = [
        f"## UFC Predictions: {event_title}",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "| Red corner | Blue corner | Weight class | Predicted winner | Confidence | Your bet (risking $100 total) |",
        "|---|---|---|---|---|---|",
    ]
    for p in predictions:
        lines.append(
            f"| {p['fighter1']} | {p['fighter2']} | {p.get('weight_class', '?')} "
            f"| **{p['prediction']}** | {p['confidence']} | {p.get('stake', '-')} |"
        )
    lines += [
        "",
        "_XGBoost + LightGBM ensemble; confidence calibrated on walk-forward CV._",
        "_Bet column: how to place a total of $100 — your maximum possible loss "
        "— across the card. The $100 is split over every side priced below the "
        "model's probability, proportional to Kelly edge; stakes always sum to "
        "$100. The bet can be on the fighter the model predicts to lose: a "
        "near-coin-flip the market prices as a lock is value on the underdog. "
        "The model's edge over bookmakers is unproven — only risk what you're "
        "happy to lose._",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fights-json", required=True, help="JSON file with the fight card")
    parser.add_argument("--event-title", default="Upcoming UFC Event")
    parser.add_argument("--event-country", default=None,
                        help="Host country of the card, e.g. USA (feeds home-crowd features)")
    args = parser.parse_args()

    with open(args.fights_json) as f:
        fights = json.load(f)

    predictions = make_predictions(fights, load_history(), load_artifacts(),
                                   event_country=args.event_country)
    if not predictions:
        raise SystemExit("No predictions produced")

    md = format_predictions_markdown(args.event_title, predictions)
    with open("predictions_output.md", "w") as f:
        f.write(md)
    # card.json goes to weekly-predictions-log beside predictions_output.md so
    # any future model can replay the same card+odds (the $100 replay metric
    # in EXPERIMENTS.md).
    if os.path.abspath(args.fights_json) != os.path.abspath("card.json"):
        shutil.copy(args.fights_json, "card.json")
    print(md)
    logger.info("Wrote predictions_output.md and card.json")


if __name__ == "__main__":
    main()
