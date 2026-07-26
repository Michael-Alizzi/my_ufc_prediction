# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A UFC fight-outcome predictor: an XGBoost + LightGBM ensemble trained on engineered fighter/fight
history, served through a small Streamlit app. `ufc_prediction_claude.ipynb` is the single source of
truth for the modeling pipeline — `ufc_prediction.ipynb` is an earlier, superseded version (kept for
reference only) and `ufc_analysis.ipynb` is an unrelated exploratory-analysis notebook, not part of
the prediction pipeline.

Raw data (`raw_fight_data.csv`, `raw_fighter_details.csv`) is produced by a separate sibling scraper
project at `../UFC-Predictions` (its own `src/createdata/` pipeline) and copied into this repo — this
repo does not scrape data itself.

## Commands

```bash
# environment
.venv/bin/pip install -r requirements.txt

# run the full modeling pipeline non-interactively (multi-hour: dominated by the
# rolling-window CV grid search and the 100-trial Optuna search, both of which
# retrain many XGBoost models). Prefer restarting the kernel and running
# interactively in VS Code/Jupyter so you can watch progress; use nbconvert
# only when a headless run is actually wanted.
#
# When running this in the background (Claude Code), check on progress at
# most once an hour, not every 15-20 minutes. `nbconvert` only writes any
# output at the very end, so there is nothing new to see on a shorter cadence
# regardless -- more frequent polling just burns context for no signal.
.venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 ufc_prediction_claude.ipynb

# serve predictions in a browser (needs ensemble.joblib + fighter_history.parquet,
# both produced by running the notebook through its last two cells)
.venv/bin/streamlit run app.py

# sanity-check the serving logic (assert-based, no framework)
.venv/bin/python test_predict.py
```

There is no lint/build config or test framework in this repo beyond `test_predict.py`.

## Architecture

**Notebook pipeline stages** (in execution order — cell order in the `.ipynb` is meaningful and has
been hand-edited via direct JSON manipulation rather than the Jupyter UI, see gotcha below):

1. Load raw CSVs → clean/normalize columns → merge fighter details onto fight rows by
   lowercased/trimmed name.
2. Feature engineering, each producing `r_*`/`b_*` paired columns computed from **prior fights only**
   (no lookahead): career avg/median stats, win/loss streaks, fight frequency, matchup diffs,
   head-to-head record, KO/submission finish rates, and Elo rating (the one feature computed via a
   sequential chronological loop rather than a vectorised cumsum, since each fight's rating depends
   on both fighters' evolving state).
3. Target/feature selection → correlation check → **rolling-window grid search** to pick how much
   trailing history to train on → **Optuna** hyperparameter search evaluated with the same
   walk-forward CV scheme (never a plain train/test split).
4. Final holdout split: validation slice (threshold/blend tuning) + test slice (scored once).
5. Ensemble: top-3 Optuna trials + one LightGBM model, blended at whichever mixing weight scores best
   on validation.
6. Decision layer, stability checks, and export — see gotchas below for why several of these exist.

**Serving path** (`predict.py` + `app.py`): reimplements the notebook's single-fight-prediction cell
against two exported artifacts — `ensemble.joblib` (trained models, blend weight, threshold, feature
schema; fully self-contained, no retraining needed) and `fighter_history.parquet` (engineered fight
history, for per-fighter lookups and head-to-head). `ensemble_baseline.joblib` is a manually-taken
snapshot of a *previous* run's `ensemble.joblib`, kept around only so the notebook's McNemar cell can
paired-compare a new experiment against it — re-copy it yourself (`cp ensemble.joblib
ensemble_baseline.joblib`) before each new experiment you want a baseline for; nothing does this
automatically.

## Gotchas (each of these was a real, previously-shipped bug — don't reintroduce them)

- **`mirror_fights()`** doubles training data by swapping red/blue corners and flipping the label, to
  stop the model learning a red-corner bias (fights list the favourite as red more often than not).
  Any new feature must follow the `r_*`/`b_*`/`*_diff` naming convention or the swap silently skips it.
- **The decision threshold is fixed at 0.5 on purpose**, not tuned or calibrated. An earlier version
  fit Platt scaling and a tuned threshold on the ~120-fight validation slice and it cost 6 points of
  test accuracy from overfitting that small a sample. Don't reintroduce calibration without pooling
  many out-of-fold predictions first (see the `ponytail:` comment in the Threshold Selection cell).
- **`last_row()`** (in both the notebook and `predict.py`) must reorient a fighter's most recent fight
  row when they fought in the blue corner last time — otherwise the `r_`-prefixed columns silently
  describe their opponent instead of them. This was a real bug, only caught by `test_predict.py`'s
  corner-swap symmetry check.
- **Duplicate fight rows**: 1990s multi-fight tournament nights create many-to-many merge artifacts
  (~950 phantom duplicate rows). The pipeline explicitly deduplicates on `(r_fighter, b_fighter,
  date)` before computing head-to-head/Elo features — don't skip it.
- **Notebook cell order vs. kernel state can diverge.** Cells have been reordered by direct file edits
  several times in this project's history, which has caused real `NameError`s when a cell's own code
  ended up positioned before the cell defining a variable it needs. After any edit to the `.ipynb`
  file, verify the resulting cell order, and always validate with a clean **Restart + Run All** rather
  than resuming a kernel that has stale state from before the edit.
- **Single-test-set metrics are noisy.** The final test set is ~110 fights; its accuracy has a 95% CI
  of roughly ±9 points. Compare experiments using the notebook's Test Set Stability Check (CLT
  interval + monthly-batch breakdown) and Paired Comparison / McNemar cells, not raw point-estimate
  deltas.
- **GPU usage (`device="cuda"`) is hardcoded** in `create_xgb_model()`, the Optuna objective, and the
  final refit. If running without a GPU, all three need to change together.

## ML Guidelines (rules; see Architecture and Gotchas above for the concrete implementation)

- **Never use a random/shuffled train-test split** (`train_test_split(..., shuffle=True)`, k-fold CV,
  etc.) anywhere in this pipeline. All validation is chronological: rolling-window walk-forward CV
  (`train_test_windows_by_month`) for model/window/hyperparameter selection, then a single
  chronological holdout (validation slice + test slice) scored once.
- **The ensemble is XGBoost + LightGBM**, not a swappable algorithm choice: top-3 Optuna-tuned XGBoost
  trials blended with one LightGBM model at a validation-selected mixing weight. Extend it by adding
  trials or one more diverse model, not by replacing the algorithm family.
- **Minimalist style**: prefer one parameterized function over near-duplicate cells (e.g. an
  `agg`/`prefix` argument instead of separate avg/median blocks), and build column lists
  programmatically from `stat_cols` rather than hand-typing every `avg_r_*`/`med_b_*` name. Don't add
  config knobs with no caller.
