"""Single-fight serving logic: the ONE implementation used by the Streamlit
app, the weekly predictions job, and the notebook's Single Fight Prediction
cell (which imports build_features from here rather than keeping a copy --
a diverged copy is how half the serving features once came from the wrong
fighter). Consumes the notebook's exports: ensemble.joblib (models, blend
weight, threshold, feature schema, diff_pairs) and fighter_history.parquet
(engineered fight history for per-fighter lookups and head-to-head).
"""
import joblib
import numpy as np
import pandas as pd


# Serving-side copy of the notebook's country aliasing (Feature: Home Crowd
# cell): Wikidata's formal country labels vs. ufcstats' location spellings.
COUNTRY_ALIASES = {
    "united states of america": "usa",
    "united states": "usa",
    "people's republic of china": "china",
    "kingdom of the netherlands": "netherlands",
    "czechia": "czech republic",
    "republic of ireland": "ireland",
}


def home_crowd_flag(fighter_country, event_country):
    """1.0 if any of the fighter's citizenship countries matches the event's
    host country, 0.0 if none do, NaN when either side is unknown."""
    if event_country is None or fighter_country is None or pd.isna(fighter_country):
        return np.nan
    countries = {
        COUNTRY_ALIASES.get(c.strip().lower(), c.strip().lower())
        for c in str(fighter_country).split(";")
        if c.strip()
    }
    if not countries:
        return np.nan
    ec = str(event_country).strip().lower()
    return float(COUNTRY_ALIASES.get(ec, ec) in countries)


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
    # History is exported date-sorted (asserted by test_pipeline_logic), so
    # the last match IS the most recent fight -- no per-call re-sort.
    row = matches.iloc[-1]
    if row["b_fighter"] == f:
        row = _reorient_to_red(row)
    return row


def own_value(row, col):
    """Read `col` as the value belonging to the fighter this row was
    reoriented FOR. last_row() guarantees the r_/avg_r_/med_r_ side describes
    that fighter, so b_-named features must be read from the r_-named partner
    -- reading them directly returns the fighter's LAST OPPONENT's stats,
    which is exactly the serving bug this function exists to prevent."""
    for b_prefix, r_prefix in (("avg_b_", "avg_r_"), ("med_b_", "med_r_"), ("b_", "r_")):
        if col.startswith(b_prefix):
            return row[r_prefix + col[len(b_prefix):]]
    return row[col]


def build_diff_pairs(feature_names, columns):
    """Map every *_diff feature to its exact (r_col, b_col) source pair.

    The notebook verifies this map numerically at export time and stores it
    in ensemble.joblib; this builder doubles as the fallback for artifacts
    that predate the stored map. Raises on any diff it cannot resolve --
    silently serving 0 for unresolved diffs is how 25 features went dead in
    production."""
    # Diffs whose source names aren't derivable by prefixing alone
    # (unit suffixes dropped, plural "wins")
    special = {
        "height_diff": ("r_height_cm", "b_height_cm"),
        "weight_diff": ("r_weight_kg", "b_weight_kg"),
        "reach_diff": ("r_reach_cm", "b_reach_cm"),
        "h2h_win_diff": ("r_h2h_wins", "b_h2h_wins"),
    }
    cols = set(columns)
    pairs = {}
    for feat in feature_names:
        if not feat.endswith("_diff"):
            continue
        if feat in special:
            pairs[feat] = special[feat]
            continue
        base = feat[: -len("_diff")]
        candidates = [(f"r_{base}", f"b_{base}")]
        for stat_prefix in ("avg_", "med_"):
            if base.startswith(stat_prefix):
                stat = base[len(stat_prefix):]
                candidates.append(
                    (f"{stat_prefix}r_{stat}", f"{stat_prefix}b_{stat}")
                )
        match = next(
            ((r, b) for r, b in candidates if r in cols and b in cols), None
        )
        if match is None:
            raise ValueError(f"Cannot resolve source columns for {feat!r}")
        pairs[feat] = match
    return pairs


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
                    history, feature_names, dtypes, event_country=None,
                    diff_pairs=None, odds_r=None, odds_b=None):
    red, blue = red.lower().strip(), blue.lower().strip()
    r_last = last_row(red, history)
    b_last = last_row(blue, history)
    n_prev, r_h2h, b_h2h = head_to_head(red, blue, history)
    if diff_pairs is None:
        diff_pairs = build_diff_pairs(feature_names, history.columns)

    predict_dict = {
        "title_fight": int(title_fight),
        "h2h_fight_count": n_prev,
        "r_h2h_wins": r_h2h,
        "b_h2h_wins": b_h2h,
        "h2h_win_diff": r_h2h - b_h2h,
        "weight_class": weight_class,
        "total_round_number": total_round_number,
        # Upcoming fights are always contested under the current ruleset;
        # without this the generic fallback below would inherit rules_era
        # from the fighter's last fight row. Dropped by reindex if the
        # loaded artifacts predate the feature.
        "rules_era": 2,
        # Home-crowd depends on the UPCOMING event's country -- never inherit
        # it from where each fighter's last fight happened. NaN (unknown) when
        # no event_country is given or the history predates the country
        # column; like rules_era, dropped by reindex on older artifacts.
        "r_home_crowd": home_crowd_flag(r_last.get("r_country"), event_country),
        "b_home_crowd": home_crowd_flag(b_last.get("b_country"), event_country),
        # Market-implied probability comes from the UPCOMING fight's closing
        # odds (vig-free) -- like home_crowd, never inherited from a last-fight
        # row. NaN when odds aren't supplied; dropped by reindex on odds-blind
        # artifacts. (EXPERIMENTS.md entry 5)
        "r_market_prob": ((1 / odds_r) / (1 / odds_r + 1 / odds_b)
                          if odds_r and odds_b else np.nan),
    }
    predict_dict["b_market_prob"] = 1 - predict_dict["r_market_prob"]
    predict_dict["home_crowd_diff"] = (
        predict_dict["r_home_crowd"] - predict_dict["b_home_crowd"]
    )

    # Both last-fight rows are reoriented so their r_/avg_r_/med_r_ side is
    # that fighter's own value. Red-side features read straight off r_last;
    # blue-side features read the r_-named partner off b_last (own_value);
    # diffs are red's own minus blue's own via the exact diff_pairs map.
    for col in feature_names:
        if col in predict_dict:
            continue
        if col.endswith("_diff"):
            r_col, b_col = diff_pairs[col]
            predict_dict[col] = r_last[r_col] - own_value(b_last, b_col)
        elif col.startswith(("r_", "avg_r_", "med_r_")):
            predict_dict[col] = r_last[col]
        elif col.startswith(("b_", "avg_b_", "med_b_")):
            predict_dict[col] = own_value(b_last, col)
        else:
            # Shared fight-context columns (e.g. gender) from red's last fight
            predict_dict[col] = r_last.get(col, 0)

    X_pred = pd.DataFrame([predict_dict]).reindex(columns=feature_names, fill_value=0)
    X_pred = X_pred.astype(dtypes.to_dict())

    cat_cols = [c for c in X_pred.columns if X_pred[c].dtype.name == "category"]
    bad = [c for c in cat_cols if X_pred[c].isna().any()]
    if bad:
        raise ValueError(f"Value not seen in training data for: {bad}")
    return X_pred


def kelly_edge(p, odds):
    """Kelly fraction for backing a side at decimal `odds` given model
    probability `p`, or 0.0 when the market price offers no edge."""
    edge = p * odds - 1
    return edge / (odds - 1) if edge > 0 else 0.0


class CatBoostOnFrame:
    """CatBoostClassifier over a pandas frame with category dtypes.

    XGBoost/LightGBM accept category columns with NaN natively; CatBoost
    refuses NaN in categorical features. This wrapper fills categorical NaN
    with a literal 'missing' level and passes cat_features by column name,
    keeping the generic ``model_class(**params).fit(X, y)`` contract used by
    the walk-forward harness, the Optuna objectives, and serving.
    """

    def __init__(self, **params):
        self.params = params

    @staticmethod
    def _frame(X):
        X = X.copy()
        for c in X.columns:
            if X[c].dtype.name == "category":
                if "missing" not in X[c].cat.categories:
                    X[c] = X[c].cat.add_categories("missing")
                X[c] = X[c].fillna("missing")
        return X

    def fit(self, X, y):
        from catboost import CatBoostClassifier
        X = self._frame(X)
        cats = [c for c in X.columns if X[c].dtype.name == "category"]
        self.model_ = CatBoostClassifier(cat_features=cats, **self.params)
        self.model_.fit(X, y)
        return self

    def predict_proba(self, X):
        return self.model_.predict_proba(self._frame(X))


class TabPFNOnFrame:
    """TabPFNClassifier over a pandas frame with category dtypes.

    TabPFN wants numeric arrays with categorical columns declared by index.
    Category columns are mapped to their fixed dtype codes (NaN preserved --
    TabPFN handles missing values natively), keeping the generic
    ``model_class(**params).fit(X, y)`` contract used by the walk-forward
    harness and serving. Codes are stable across fit/predict because every
    frame carries the same categorical dtypes (X_train.dtypes).
    """

    def __init__(self, **params):
        self.params = params

    @staticmethod
    def _array(X):
        X = X.copy()
        cat_idx = []
        for i, c in enumerate(X.columns):
            if X[c].dtype.name == "category":
                cat_idx.append(i)
                codes = X[c].cat.codes.astype("float64")
                X[c] = codes.where(codes >= 0)  # -1 (NaN) back to NaN
        return X.astype("float64").to_numpy(), cat_idx

    def fit(self, X, y):
        from tabpfn import TabPFNClassifier
        Xa, cat_idx = self._array(X)
        self.model_ = TabPFNClassifier(
            categorical_features_indices=cat_idx or None, **self.params)
        self.model_.fit(Xa, y)
        return self

    def predict_proba(self, X):
        return self.model_.predict_proba(self._array(X)[0])


def _logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def blend_proba(X, models, lgbm, lgbm_weight, extra=None, extra_weight=0.0,
                space="linear"):
    """Ensemble probability; `extra` is any third member with predict_proba
    (CatBoostOnFrame in run 8a, TabPFNOnFrame in run 8b).

    `space` selects the pooling rule (EXPERIMENTS.md entry 8c): "linear"
    averages probabilities (pre-8c artifacts); "logit" averages log-odds —
    sharper where members agree, the standard pool when the metric is
    log-loss. Serving reads it from the artifact's blend_space key so old
    artifacts keep their original arithmetic.
    """
    xgb_p = np.mean([m.predict_proba(X)[:, 1] for m in models], axis=0)
    lgb_p = lgbm.predict_proba(X)[:, 1]
    if space == "logit":
        z = (1 - lgbm_weight - extra_weight) * _logit(xgb_p) \
            + lgbm_weight * _logit(lgb_p)
        if extra is not None and extra_weight:
            z = z + extra_weight * _logit(extra.predict_proba(X)[:, 1])
        return 1.0 / (1.0 + np.exp(-z))
    p = (1 - lgbm_weight - extra_weight) * xgb_p + lgbm_weight * lgb_p
    if extra is not None and extra_weight:
        p = p + extra_weight * extra.predict_proba(X)[:, 1]
    return p


def predict_winner(red, blue, weight_class, title_fight, total_round_number,
                    history, artifacts, event_country=None,
                    odds_r=None, odds_b=None):
    """Returns (winner_name, calibrated_probability_red_wins).

    The winner is decided on the raw ensemble score at best_th (a dedicated
    experiment confirmed retuning that decision on calibrated scores doesn't
    beat it); calibration only reshapes the probability shown to the user so
    it tracks real win frequency, via Platt scaling fit on pooled walk-forward
    CV predictions (see the notebook's Probability Calibration section).
    """
    X_pred = build_features(
        red, blue, weight_class, title_fight, total_round_number,
        history, artifacts["feature_names"], artifacts["dtypes"],
        event_country=event_country,
        diff_pairs=artifacts.get("diff_pairs"),
        odds_r=odds_r, odds_b=odds_b,
    )
    raw_proba = float(blend_proba(
        X_pred, artifacts["models"], artifacts["lgbm"], artifacts["lgbm_weight"],
        extra=artifacts.get("extra_model"), extra_weight=artifacts.get("extra_weight", 0.0),
        space=artifacts.get("blend_space", "linear")
    )[0])
    winner = red if raw_proba >= artifacts["best_th"] else blue
    # Calibrator is fit on the score centered at 0.5 (fit_intercept=False)
    # so raw=0.5 always maps to calibrated=0.5 -- the decision above and the
    # displayed confidence can never disagree about who's favored.
    calibrated_proba = float(
        artifacts["calibrator"].predict_proba([[raw_proba - 0.5]])[0, 1]
    )
    return winner, calibrated_proba
