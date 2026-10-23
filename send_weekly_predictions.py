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
import sys
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

RULE_NAMES = {"A": "kelly value", "C": "vig floor", "E": "shrunk staking",
              "F": "fitted blend"}


def make_predictions(fights, history, artifacts, event_country=None, bankroll=100):
    """Predict each fight and size every rule's bets.

    Each rule (A/C/E/F, see RULE_NAMES) picks at most one value side per
    fight; each rule then splits the whole bankroll across its own picks,
    proportionally to Kelly fraction. The value side can be the fighter the
    model predicts to LOSE (a narrow pick priced by the market as a lock).
    Per prediction: "picks" = {rule: (name, odds, kelly)}, "stakes" =
    {rule: (name, odds, dollars)}. Which rule is the real bet is applied
    separately by stake_slip().
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
            picks = {"A": (bet_on, bet_odds, kelly)} if kelly > 0 else {}

            # Rules C (vig floor), E (shrunk staking) and F (fitted blend).
            # C/E: EXPERIMENTS.md entry 9 (beat A on the full backtest but
            # tripped the halves-consistency clause). F: entry 10 — logit-space
            # blend of model and vig-free market at the model-trust weight
            # fitted on the pooled-OOF pool (frozen). Which rule is staked is
            # decided by the block promotion test (entry 11).
            if fight.get("odds1") and fight.get("odds2"):
                o1, o2 = float(fight["odds1"]), float(fight["odds2"])
                vig = 1 / o1 + 1 / o2 - 1
                e1, e2 = proba * o1 - 1, (1 - proba) * o2 - 1
                if max(e1, e2) > vig:
                    n, p_, o_ = ((fight["fighter1"], proba, o1) if e1 > e2
                                 else (fight["fighter2"], 1 - proba, o2))
                    picks["C"] = (n, o_, kelly_edge(p_, o_))
                imp1 = (1 / o1) / (1 / o1 + 1 / o2)
                ps = (proba + imp1) / 2
                for n, p_, o_ in ((fight["fighter1"], ps, o1),
                                  (fight["fighter2"], 1 - ps, o2)):
                    k = kelly_edge(p_, o_)
                    if k > 0:
                        picks["E"] = (n, o_, k)
                logit = lambda x: math.log(x / (1 - x))  # noqa: E731
                pc = min(max(proba, 1e-6), 1 - 1e-6)
                pf = 1 / (1 + math.exp(-(LAMBDA_F * logit(pc)
                                         + (1 - LAMBDA_F) * logit(imp1))))
                for n, p_, o_ in ((fight["fighter1"], pf, o1),
                                  (fight["fighter2"], 1 - pf, o2)):
                    k = kelly_edge(p_, o_)
                    if k > 0:
                        picks["F"] = (n, o_, k)

            predictions.append({
                "fighter1": fight["fighter1"],
                "fighter2": fight["fighter2"],
                "weight_class": weight_class,
                "prediction": winner.title(),
                "confidence": f"{confidence:.1%}",
                "has_odds": has_odds,
                "picks": picks,
                "stakes": {},
            })
        except Exception as e:
            logger.error(f"Prediction failed for {fight['fighter1']} vs {fight['fighter2']}: {e}")
            predictions.append({
                "fighter1": fight["fighter1"], "fighter2": fight["fighter2"],
                "weight_class": fight.get("weight_class", "?"),
                "prediction": "error", "confidence": "-",
            })
            continue

    # Each rule splits the whole bankroll over its own picks, proportional to
    # Kelly. A kelly edge can be real but too small to earn even $1 -- drop
    # those (re-checking, since removing one can push the next-smallest
    # below $1 too); the rounding remainder goes to the biggest edge.
    for rule in RULE_NAMES:
        pool = [p for p in predictions if rule in p.get("picks", {})]
        while pool:
            total = sum(p["picks"][rule][2] for p in pool)
            amts = [round(bankroll * p["picks"][rule][2] / total) for p in pool]
            if all(amts):
                break
            pool = [p for p, a in zip(pool, amts) if a]
        if not pool:
            continue
        top = max(range(len(pool)), key=lambda i: pool[i]["picks"][rule][2])
        amts[top] += bankroll - sum(amts)
        for p, a in zip(pool, amts):
            name, o, _ = p["picks"][rule]
            p["stakes"][rule] = (name, o, a)

    return predictions


def stake_slip(predictions, staked_rule):
    """Present staked_rule's split as the real bet and the other rules as
    shadow strings. Sets bet_on/bet_odds/kelly/stake_amt/stake/shadow."""
    for p in predictions:
        if "picks" not in p:
            continue
        p["bet_on"], p["bet_odds"], p["kelly"] = p["picks"].get(staked_rule, (None, None, 0.0))
        if staked_rule in p["stakes"]:
            name, o, a = p["stakes"][staked_rule]
            p["stake_amt"] = a
            p["stake"] = f"${a} on {name.title()} (@{o:.2f}, returns ~${round(a * o)})"
        else:
            p["stake"] = "$0 (no value)" if p["has_odds"] else "-"
        p["shadow"] = " / ".join(f"{r}: ${a} on {n.title()} (@{o:.2f})"
                                 for r, (n, o, a) in p["stakes"].items()
                                 if r != staked_rule) or "-"
    return predictions


def format_predictions_markdown(event_title, predictions, bankroll, staked_rule):
    shadows = " / ".join(f"{r} {n}" for r, n in RULE_NAMES.items() if r != staked_rule)
    lines = [
        f"## UFC Predictions: {event_title}",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        f"| Red corner | Blue corner | Weight class | Predicted winner | Confidence | Your bet: rule {staked_rule} {RULE_NAMES[staked_rule]} (risking ${bankroll} total) | Shadow rules ({shadows}, not staked) |",
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
        f"— across the card. The ${bankroll} is split over the staked rule's value "
        "bets, proportional to Kelly edge; stakes always sum to "
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

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
    from promotion_test import staked_rule_from_log
    staked_rule = staked_rule_from_log()
    logger.info(f"Staked rule (EXPERIMENTS.md entry 11 block test): {staked_rule}")

    predictions = make_predictions(fights, load_history(), load_artifacts(),
                                   event_country=args.event_country,
                                   bankroll=args.bankroll)
    if not predictions:
        raise SystemExit("No predictions produced")
    stake_slip(predictions, staked_rule)

    md = format_predictions_markdown(args.event_title, predictions,
                                     args.bankroll, staked_rule)
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
