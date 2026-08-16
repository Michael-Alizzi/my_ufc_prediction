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
import math
import os
import shutil
from datetime import datetime

import pandas as pd

from predict import kelly_edge, load_artifacts, load_history, predict_winner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rule F's model-trust weight (EXPERIMENTS.md entry 10): share of the say the
# model's logit gets vs the vig-free market's. Fitted once by maximum
# likelihood on the full pooled-OOF-with-odds set (5,786 fights, Aug 2026)
# and FROZEN for the forward trial — never refit mid-trial.
LAMBDA_F = 0.746


def make_predictions(fights, history, artifacts, event_country=None, bankroll=100):
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
                # Feature slot: de-vigged multi-book median when the card
                # carries one (scripts/fetch_card_odds.py) — the model's
                # market-opinion input. Staking below always uses odds1/odds2
                # (Sportsbet, the bettable price). Two-slot design: entry 9
                # follow-up, 2026-08-11.
                odds_r=fight.get("feat_odds1", fight.get("odds1")),
                odds_b=fight.get("feat_odds2", fight.get("odds2")),
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

            # Shadow rules C (vig floor), E (shrunk staking) and F (fitted
            # blend) — logged alongside the production rule A, never staked.
            # C/E: EXPERIMENTS.md entry 9 (beat A on the full backtest but
            # tripped the halves-consistency clause). F: entry 10 — logit-space
            # blend of model and vig-free market at the model-trust weight
            # fitted on the pooled-OOF pool (frozen; never refit mid-trial).
            # The forward record logged here adjudicates on held-out cards.
            shadow = {}
            if fight.get("odds1") and fight.get("odds2"):
                o1, o2 = float(fight["odds1"]), float(fight["odds2"])
                vig = 1 / o1 + 1 / o2 - 1
                e1, e2 = proba * o1 - 1, (1 - proba) * o2 - 1
                if max(e1, e2) > vig:
                    n, p_, o_ = ((fight["fighter1"], proba, o1) if e1 > e2
                                 else (fight["fighter2"], 1 - proba, o2))
                    shadow["C"] = (n, o_, kelly_edge(p_, o_))
                imp1 = (1 / o1) / (1 / o1 + 1 / o2)
                ps = (proba + imp1) / 2
                for n, p_, o_ in ((fight["fighter1"], ps, o1),
                                  (fight["fighter2"], 1 - ps, o2)):
                    k = kelly_edge(p_, o_)
                    if k > 0:
                        shadow["E"] = (n, o_, k)
                logit = lambda x: math.log(x / (1 - x))  # noqa: E731
                pc = min(max(proba, 1e-6), 1 - 1e-6)
                pf = 1 / (1 + math.exp(-(LAMBDA_F * logit(pc)
                                         + (1 - LAMBDA_F) * logit(imp1))))
                for n, p_, o_ in ((fight["fighter1"], pf, o1),
                                  (fight["fighter2"], 1 - pf, o2)):
                    k = kelly_edge(p_, o_)
                    if k > 0:
                        shadow["F"] = (n, o_, k)

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
                "shadow": shadow,
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
            p["stake_amt"] = round(bankroll * p["kelly"] / total)
        max(value, key=lambda p: p["kelly"])["stake_amt"] += bankroll - sum(
            p["stake_amt"] for p in value
        )
        for p in value:
            payout = round(p["stake_amt"] * p["bet_odds"])
            p["stake"] = (
                f"${p['stake_amt']} on {p['bet_on'].title()} "
                f"(@{p['bet_odds']:.2f}, returns ~${payout})"
            )

    # Shadow bankrolls: each rule's own $100 split, display-only.
    for rule in ("C", "E", "F"):
        picks = [p for p in predictions if p.get("shadow", {}).get(rule)]
        total = sum(p["shadow"][rule][2] for p in picks)
        for p in picks:
            name, o, k = p["shadow"][rule]
            amt = round(bankroll * k / total) if total else 0
            p.setdefault("shadow_txt", []).append(
                f"{rule}: ${amt} on {name.title()} (@{o:.2f})")
    for p in predictions:
        p["shadow"] = " / ".join(p.get("shadow_txt", [])) or "-"
        p.pop("shadow_txt", None)

    return predictions


def format_predictions_markdown(event_title, predictions, bankroll=100):
    lines = [
        f"## UFC Predictions: {event_title}",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        f"| Red corner | Blue corner | Weight class | Predicted winner | Confidence | Your bet (risking ${bankroll} total) | Shadow rules (C vig-floor / E shrunk / F fitted-blend, not staked) |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in predictions:
        lines.append(
            f"| {p['fighter1']} | {p['fighter2']} | {p.get('weight_class', '?')} "
            f"| **{p['prediction']}** | {p['confidence']} | {p.get('stake', '-')} "
            f"| {p.get('shadow', '-')} |"
        )
    lines += [
        "",
        "_XGBoost + LightGBM + CatBoost, stacked on walk-forward OOF; confidence calibrated the same way._",
        f"_Bet column: how to place a total of ${bankroll} — your maximum possible loss "
        f"— across the card. The ${bankroll} is split over every side priced below the "
        "model's probability, proportional to Kelly edge; stakes always sum to "
        f"${bankroll}. The bet can be on the fighter the model predicts to lose: a "
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
    parser.add_argument("--bankroll", type=int, default=50,
                        help="Total dollars risked across the card (default 50)")
    args = parser.parse_args()

    with open(args.fights_json) as f:
        fights = json.load(f)

    predictions = make_predictions(fights, load_history(), load_artifacts(),
                                   event_country=args.event_country,
                                   bankroll=args.bankroll)
    if not predictions:
        raise SystemExit("No predictions produced")

    md = format_predictions_markdown(args.event_title, predictions,
                                     bankroll=args.bankroll)
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
