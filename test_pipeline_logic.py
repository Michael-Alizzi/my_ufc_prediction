"""pytest checks for the modeling pipeline: training-matrix shape sanity and
data-leak guards. Run: .venv/bin/pytest test_pipeline_logic.py -v

Requires ensemble.joblib and fighter_history.parquet (produced by the
notebook's "Export for Streamlit App" cell) -- these are checked in fixtures
below rather than regenerated, since the notebook run is multi-hour.
"""
import joblib
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def artifacts():
    return joblib.load("ensemble.joblib")


@pytest.fixture(scope="module")
def history():
    return pd.read_parquet("fighter_history.parquet")


def test_feature_matrix_shape_matches_dtypes(artifacts):
    feats = artifacts["feature_names"]
    assert len(feats) == len(artifacts["dtypes"])
    assert len(feats) == len(set(feats)), "duplicate feature name in training matrix"


def test_all_trained_features_derivable_from_history(artifacts, history):
    missing = [c for c in artifacts["feature_names"] if c not in history.columns]
    assert not missing, f"trained feature not present in fighter_history.parquet: {missing}"


def test_label_and_identifiers_excluded_from_features(artifacts):
    feats = set(artifacts["feature_names"])
    leaked = feats & {"r_win", "winner", "date_d", "fight_id", "r_fighter", "b_fighter"}
    assert not leaked, f"label/identifier column present in training features: {leaked}"


def test_every_corner_feature_has_a_mirror_partner(artifacts):
    """mirror_fights() silently skips swapping any r_/b_ column whose partner
    is missing (see CLAUDE.md's mirror_fights gotcha) -- a corner feature with
    no partner keeps its original, unswapped value in mirror-augmented rows
    even though the label flips, corrupting that column's training signal."""
    feats = set(artifacts["feature_names"])
    unpaired = []
    for c in sorted(feats):
        for red, blue in (("avg_r_", "avg_b_"), ("med_r_", "med_b_"), ("r_", "b_")):
            if c.startswith(red):
                partner = blue + c[len(red):]
                if partner not in feats:
                    unpaired.append((c, partner))
                break
            if c.startswith(blue):
                partner = red + c[len(blue):]
                if partner not in feats:
                    unpaired.append((c, partner))
                break
    assert not unpaired, f"columns with no mirror partner: {unpaired}"


def test_no_duplicate_fight_rows(history):
    dupes = int(history.duplicated(subset=["r_fighter", "b_fighter", "date_d"]).sum())
    assert dupes == 0, f"{dupes} duplicate (r_fighter, b_fighter, date_d) rows"


def test_history_sorted_chronologically(history):
    assert history["date_d"].is_monotonic_increasing


def test_debut_fights_have_no_prior_average_stats(history):
    """avg_r_*/avg_b_* must be NaN on a fighter's true first-ever appearance
    (in either corner) -- otherwise the average would be computed using the
    fight being predicted, or one after it, leaking the outcome into its own
    feature.

    Uses date_d rather than the exported fight_id column: fight_id is a
    leftover from an earlier pipeline stage and never refreshed after Cell
    30's dedup, so 5663/8310 rows are out of chronological order relative to
    date_d -- unreliable for reconstructing "first fight" post export.
    Fighters whose debut date has two fights (1990s tournament nights) are
    excluded: which of that day's two fights came first isn't recoverable
    from date_d alone, so the debut mask can't be checked unambiguously.
    """
    long = pd.concat([
        history[["r_fighter", "date_d"]].rename(columns={"r_fighter": "fighter"}),
        history[["b_fighter", "date_d"]].rename(columns={"b_fighter": "fighter"}),
    ])
    first_date = long.groupby("fighter")["date_d"].min()
    fights_on_debut_date = long.groupby("fighter").apply(
        lambda g: (g["date_d"] == first_date[g.name]).sum(), include_groups=False
    )
    unambiguous_debut_fighters = set(fights_on_debut_date[fights_on_debut_date == 1].index)

    def is_unambiguous_debut(fighter_col):
        return (
            (history["date_d"] == history[fighter_col].map(first_date))
            & history[fighter_col].isin(unambiguous_debut_fighters)
        )

    is_debut_r = is_unambiguous_debut("r_fighter")
    is_debut_b = is_unambiguous_debut("b_fighter")

    avg_r_cols = [c for c in history.columns if c.startswith("avg_r_")]
    avg_b_cols = [c for c in history.columns if c.startswith("avg_b_")]

    assert history.loc[is_debut_r, avg_r_cols].isna().all().all()
    assert history.loc[is_debut_b, avg_b_cols].isna().all().all()
