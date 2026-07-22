"""Prediction logic shared by the Streamlit app and its self-check.

Reimplements the notebook's single-fight prediction cell (ufc_prediction_claude.ipynb,
"Single Fight Prediction" section) against the artifacts it exports:
ensemble.joblib (trained models) and fighter_history.parquet (engineered fight
history, for per-fighter lookups and head-to-head).
"""
import joblib
import numpy as np
import pandas as pd


def load_artifacts(path="ensemble.joblib"):
    return joblib.load(path)


def load_history(path="fighter_history.parquet"):
    return pd.read_parquet(path)


def list_fighters(history):
    """Sorted, title-cased fighter names for display."""
    names = pd.concat([history["r_fighter"], history["b_fighter"]]).unique()
    return sorted(n.title() for n in names)


def _reorient_to_red(row):
    """Swap r_/b_ prefixed values so r_ always describes `row`'s own
    fighter. Same rule as the notebook's mirror_fights, applied to one
    historical row instead of a training batch: a fighter's last fight may
    have had them in the blue corner, in which case the raw r_ columns
    describe their opponent, not them.
    """
    swap = {}
    for c in row.index:
        for red_prefix, blue_prefix in (("avg_r_", "avg_b_"), ("med_r_", "med_b_"), ("r_", "b_")):
            if c.startswith(red_prefix):
                partner = blue_prefix + c[len(red_prefix):]
                if partner in row.index:
                    swap[c] = partner
                break
            if c.startswith(blue_prefix):
                partner = red_prefix + c[len(blue_prefix):]
                if partner in row.index:
                    swap[c] = partner
                break
    reoriented = row.rename(swap)[row.index]
    diff_cols = [c for c in row.index if c.endswith("_diff")]
    reoriented[diff_cols] = -reoriented[diff_cols].astype(float)
    return reoriented


def last_row(fighter, history):
    f = fighter.lower().strip()
    matches = history[(history["r_fighter"] == f) | (history["b_fighter"] == f)]
    if matches.empty:
        raise ValueError(f"No fight history for {fighter!r}")
    row = matches.sort_values("date_d", ascending=False).iloc[0]
    if row["b_fighter"] == f:
        row = _reorient_to_red(row)
    return row


def head_to_head(red, blue, history):
    """(prior meetings, red wins, blue wins) between two fighters. Names must
    already be lowercased to match the history frame's stored values."""
    prev = history[
        ((history["r_fighter"] == red) & (history["b_fighter"] == blue))
        | ((history["r_fighter"] == blue) & (history["b_fighter"] == red))
    ]
    r_wins = int((prev["winner"] == red).sum())
    b_wins = int((prev["winner"] == blue).sum())
    return len(prev), r_wins, b_wins


def build_features(red, blue, weight_class, title_fight, total_round_number,
                    history, feature_names, dtypes):
    red, blue = red.lower().strip(), blue.lower().strip()
    r_last = last_row(red, history)
    b_last = last_row(blue, history)
    n_prev, r_h2h, b_h2h = head_to_head(red, blue, history)

    predict_dict = {
        "title_fight": int(title_fight),
        "h2h_fight_count": n_prev,
        "r_h2h_wins": r_h2h,
        "b_h2h_wins": b_h2h,
        "h2h_win_diff": r_h2h - b_h2h,
        "weight_class": weight_class,
        "total_round_number": total_round_number,
    }

    for col in feature_names:
        if col in predict_dict:
            continue
        if col.startswith("r_"):
            predict_dict[col] = r_last[col]
        elif col.startswith("b_"):
            predict_dict[col] = b_last[col]
        elif col.endswith("_diff"):
            base = col[:-5]
            r_cands = [c for c in r_last.index if c.startswith("r_") and base in c]
            b_cands = [c for c in b_last.index if c.startswith("b_") and base in c]
            predict_dict[col] = (
                r_last[r_cands[0]] - b_last[b_cands[0]]
                if len(r_cands) == 1 and len(b_cands) == 1 else 0
            )
        else:
            predict_dict[col] = r_last.get(col, 0)

    X_pred = pd.DataFrame([predict_dict]).reindex(columns=feature_names, fill_value=0)
    X_pred = X_pred.astype(dtypes.to_dict())

    cat_cols = [c for c in X_pred.columns if X_pred[c].dtype.name == "category"]
    bad = [c for c in cat_cols if X_pred[c].isna().any()]
    if bad:
        raise ValueError(f"Value not seen in training data for: {bad}")
    return X_pred


def blend_proba(X, models, lgbm, lgbm_weight):
    xgb_p = np.mean([m.predict_proba(X)[:, 1] for m in models], axis=0)
    lgb_p = lgbm.predict_proba(X)[:, 1]
    return (1 - lgbm_weight) * xgb_p + lgbm_weight * lgb_p


def predict_winner(red, blue, weight_class, title_fight, total_round_number,
                    history, artifacts):
    """Returns (winner_name, probability_red_wins)."""
    X_pred = build_features(
        red, blue, weight_class, title_fight, total_round_number,
        history, artifacts["feature_names"], artifacts["dtypes"],
    )
    proba = float(blend_proba(
        X_pred, artifacts["models"], artifacts["lgbm"], artifacts["lgbm_weight"]
    )[0])
    winner = red if proba >= artifacts["best_th"] else blue
    return winner, proba
