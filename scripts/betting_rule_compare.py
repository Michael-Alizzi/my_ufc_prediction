"""Entry 9: compare pre-registered betting rules on the pooled OOF fights
matched to closing odds. No tuned thresholds — five discrete arms (A-E,
EXPERIMENTS.md entry 9 pre-registration), each scored on flat and
kelly-proportional ROI over the full pool and both temporal halves.

Usage: betting_rule_compare.py [artifact] [--db URL]
"""
import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import odds_backtest as ob  # noqa: E402
from predict import kelly_edge  # noqa: E402


def simulate(df, pick_side):
    """pick_side(row) -> (stake_kelly, odds, won) or None. Returns metrics."""
    rows = []
    for r in df.itertuples():
        bet = pick_side(r)
        if bet is None:
            continue
        kelly, odds, won = bet
        rows.append({"kelly": min(kelly, 0.25), "odds": odds, "won": won,
                     "date": r.date_d})
    b = pd.DataFrame(rows)
    if not len(b):
        return None
    out = {}
    for label, half in (("full", b),
                        ("H1", b[b["date"] <= b["date"].median()]),
                        ("H2", b[b["date"] > b["date"].median()])):
        for scheme in ("flat", "kelly"):
            st = half["kelly"] if scheme == "kelly" else pd.Series(1.0, index=half.index)
            profit = (np.where(half["won"], half["odds"] - 1, -1) * st).sum()
            out[f"{label}_{scheme}"] = profit / st.sum()
    out["bets"] = len(b)
    out["hit"] = b["won"].mean()
    return out


def _sides(r):
    """Common per-fight quantities."""
    k_r, k_b = kelly_edge(r.proba, r.odds_r), kelly_edge(1 - r.proba, r.odds_b)
    imp_r_vf = (1 / r.odds_r) / (1 / r.odds_r + 1 / r.odds_b)
    vig = 1 / r.odds_r + 1 / r.odds_b - 1
    return k_r, k_b, imp_r_vf, vig


def arm_A(r):
    k_r, k_b, _, _ = _sides(r)
    if k_r <= 0 and k_b <= 0:
        return None
    on_red = k_r > 0
    return ((k_r if on_red else k_b),
            (r.odds_r if on_red else r.odds_b), bool(r.y) == on_red)


def arm_B(r):
    bet = arm_A(r)
    if bet is None:
        return None
    _, _, imp_r_vf, _ = _sides(r)
    fav_prob = max(imp_r_vf, 1 - imp_r_vf)
    if abs(r.proba - 0.5) <= 0.10 and fav_prob >= 0.65:
        return None  # the losing segment, carved out
    return bet


def arm_C(r):
    k_r, k_b, _, vig = _sides(r)
    edge_r, edge_b = r.proba * r.odds_r - 1, (1 - r.proba) * r.odds_b - 1
    if edge_r <= vig and edge_b <= vig:
        return None
    on_red = edge_r > edge_b
    return ((k_r if on_red else k_b),
            (r.odds_r if on_red else r.odds_b), bool(r.y) == on_red)


def arm_D(r):
    bet = arm_C(r)
    if bet is None:
        return None
    _, _, imp_r_vf, _ = _sides(r)
    edge_r = r.proba * r.odds_r - 1
    on_red = bet[1] == r.odds_r
    market_favors_red = imp_r_vf >= 0.5
    if on_red != market_favors_red:
        return None  # never fade the market's direction
    return bet


def arm_E(r):
    _, _, imp_r_vf, _ = _sides(r)
    p = (r.proba + imp_r_vf) / 2
    k_r, k_b = kelly_edge(p, r.odds_r), kelly_edge(1 - p, r.odds_b)
    if k_r <= 0 and k_b <= 0:
        return None
    on_red = k_r > 0
    return ((k_r if on_red else k_b),
            (r.odds_r if on_red else r.odds_b), bool(r.y) == on_red)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", nargs="?", default="ensemble.joblib")
    ap.add_argument("--db", default="postgresql://localhost:5432/mma_ai")
    args = ap.parse_args()

    odds = ob.load_odds(args.db)
    oof = joblib.load(args.artifact)["oof"].copy()
    df = ob.join_odds(oof, odds)
    print(f"{len(df)} OOF fights with odds\n")
    print(f"{'arm':10s} {'bets':>5s} {'hit':>6s} {'flat':>7s} {'kelly':>7s} "
          f"{'H1f':>6s} {'H2f':>6s} {'H1k':>6s} {'H2k':>6s}")
    for name, fn in (("A current", arm_A), ("B carveout", arm_B),
                     ("C vigfloor", arm_C), ("D neverfade", arm_D),
                     ("E shrunk", arm_E)):
        m = simulate(df, fn)
        if m is None:
            print(f"{name:10s}  no bets")
            continue
        print(f"{name:10s} {m['bets']:5d} {m['hit']:6.1%} {m['full_flat']:+7.1%} "
              f"{m['full_kelly']:+7.1%} {m['H1_flat']:+6.1%} {m['H2_flat']:+6.1%} "
              f"{m['H1_kelly']:+6.1%} {m['H2_kelly']:+6.1%}")


if __name__ == "__main__":
    main()
