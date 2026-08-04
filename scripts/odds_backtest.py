#!/usr/bin/env python3
"""Profitability backtest: score one or two models' pooled-OOF predictions
against historical closing odds (BestFightOdds via the locally-restored
mma-ai dump -- NEVER committed; unlicensed upstream, aggregates only).

One-time DB setup on the desktop (Postgres already runs for Optuna):

    createdb mma_ai
    pg_restore --no-owner -d mma_ai \
        /media/michael/287B-8E90/Python/mma-ai-dataset/dumps/mma-ai.postgres-custom

Run (baseline vs candidate -- e.g. deciding a tied experiment):

    python scripts/odds_backtest.py \
        .experiment_runs/run1-baseline-v2.ensemble.joblib ensemble.joblib \
        --db postgresql://localhost:5432/mma_ai

Expected schema (per mma-ai's docs): features.odds keyed by
(fight_id, fighter_id, event_id) with closing_odds, joined through
features.fighter_mapping / event_mapping / fight_mapping. If the restored
schema differs, adjust ODDS_SQL below -- discover tables with `\\dt features.*`
and report odds coverage honestly (mma-ai itself warns of nulls).

Strategies reported per model, plus the market itself as the bar to beat:
  flat   -- $1 on every value side (model prob beats implied prob)
  kelly  -- stake proportional to Kelly fraction (uncompounded)
  segment "model-close, bookies-one-sided" -- |p-0.5| <= 0.10 and
           implied favourite >= 0.65 (the strategy Michael actually bets)
"""
import argparse
import sys
import unicodedata

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from predict import kelly_edge  # noqa: E402  (single shared betting maths)

ODDS_SQL = """
    SELECT fm.fighter_name, em.event_date, o.closing_odds
    FROM features.odds o
    JOIN features.fighter_mapping fm ON fm.fighter_id = o.fighter_id
    JOIN features.event_mapping em ON em.event_id = o.event_id
    WHERE o.closing_odds IS NOT NULL AND o.closing_odds > 1.0
"""


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.lower().replace(".", "").strip()


def load_odds(db_url):
    import sqlalchemy
    odds = pd.read_sql(ODDS_SQL, sqlalchemy.create_engine(db_url))
    odds["name"] = odds["fighter_name"].map(norm)
    odds["date"] = pd.to_datetime(odds["event_date"])
    # keep one closing quote per fighter-date (median if duplicated)
    return odds.groupby(["name", "date"], as_index=False)["closing_odds"].median()


def join_odds(oof, odds):
    """OOF fights + each corner's closing odds, matched on normalized name
    and event date (exact, then +/-1 day for card-date drift)."""
    lookup = {}
    for r in odds.itertuples():
        lookup[(r.name, r.date)] = r.closing_odds
    def get(name, date):
        for delta in (0, 1, -1):
            v = lookup.get((name, date + pd.Timedelta(days=delta)))
            if v is not None:
                return v
        return np.nan
    oof = oof.copy()
    oof["date_d"] = pd.to_datetime(oof["date_d"])
    oof["odds_r"] = [get(norm(r), d) for r, d in zip(oof["r_fighter"], oof["date_d"])]
    oof["odds_b"] = [get(norm(b), d) for b, d in zip(oof["b_fighter"], oof["date_d"])]
    return oof.dropna(subset=["odds_r", "odds_b"])


def backtest(df, label):
    """df: y (1 = red won), proba (P(red)), odds_r, odds_b."""
    rows = []
    for r in df.itertuples():
        k_r, k_b = kelly_edge(r.proba, r.odds_r), kelly_edge(1 - r.proba, r.odds_b)
        if k_r <= 0 and k_b <= 0:
            continue
        on_red = k_r > 0
        kelly = k_r if on_red else k_b
        odds = r.odds_r if on_red else r.odds_b
        won = bool(r.y) == on_red
        imp_r = (1 / r.odds_r) / (1 / r.odds_r + 1 / r.odds_b)  # vig-free
        fav_prob = max(imp_r, 1 - imp_r)
        rows.append({
            "won": won, "odds": odds, "kelly": min(kelly, 0.25),
            "model_close": abs(r.proba - 0.5) <= 0.10,
            "bookies_onesided": fav_prob >= 0.65,
            "on_underdog": odds > (r.odds_b if on_red else r.odds_r),
        })
    bets = pd.DataFrame(rows)

    def roi(sub, stake_col=None):
        if not len(sub):
            return "no bets"
        stakes = sub[stake_col] if stake_col else pd.Series(1.0, index=sub.index)
        profit = (np.where(sub["won"], sub["odds"] - 1, -1) * stakes).sum()
        return (f"{len(sub)} bets, hit {sub['won'].mean():.1%}, "
                f"ROI {profit / stakes.sum():+.1%}")

    seg = bets[bets["model_close"] & bets["bookies_onesided"]] if len(bets) else bets
    print(f"\n--- {label} ({len(df)} fights with odds) ---")
    print(f"  flat  $1/value bet : {roi(bets)}")
    print(f"  kelly-proportional : {roi(bets, 'kelly')}")
    print(f"  segment close-vs-onesided: {roi(seg)}")
    if len(bets):
        print(f"  underdog share of bets: {bets['on_underdog'].mean():.0%}")
    return bets


def market_baseline(df):
    """The bar: how often the closing-line favourite wins, and the market's
    log-loss -- a model must beat THIS, not a coin flip."""
    imp_r = (1 / df["odds_r"]) / (1 / df["odds_r"] + 1 / df["odds_b"])
    fav_correct = ((imp_r >= 0.5) == df["y"].astype(bool)).mean()
    eps = 1e-9
    market_ll = -np.mean(np.where(df["y"] == 1, np.log(imp_r + eps),
                                  np.log(1 - imp_r + eps)))
    print(f"\nMarket baseline on the same fights: closing favourite wins "
          f"{fav_correct:.1%}; market log-loss {market_ll:.4f}")
    for label, proba in df.filter(like="proba_").items():
        ll = -np.mean(np.where(df["y"] == 1, np.log(proba + eps),
                               np.log(1 - proba + eps)))
        acc = ((proba >= 0.5) == df["y"].astype(bool)).mean()
        print(f"  {label}: accuracy {acc:.1%}, log-loss {ll:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifacts", nargs="+",
                    help="one or two ensemble.joblib paths (baseline [candidate])")
    ap.add_argument("--db", default="postgresql://localhost:5432/mma_ai")
    args = ap.parse_args()

    odds = load_odds(args.db)
    print(f"odds rows loaded: {len(odds)} fighter-date closing quotes")

    frames = []
    for i, path in enumerate(args.artifacts):
        art = joblib.load(path)
        if "oof" not in art:
            raise SystemExit(f"{path} has no pooled OOF (pre-baseline-v2 artifact)")
        oof = join_odds(art["oof"], odds)
        print(f"\n{path}: {len(art['oof'])} OOF fights, {len(oof)} matched to odds "
              f"({len(oof) / len(art['oof']):.0%} coverage)")
        backtest(oof, path)
        frames.append(oof.rename(columns={"proba": f"proba_{i}_{path.split('/')[-1]}"}))

    # common-fight comparison incl. the market itself
    common = frames[0]
    for f in frames[1:]:
        common = common.merge(
            f[[c for c in f.columns if c.startswith("proba_")]
              + ["r_fighter", "b_fighter", "date_d"]],
            on=["r_fighter", "b_fighter", "date_d"])
    market_baseline(common)


if __name__ == "__main__":
    main()
