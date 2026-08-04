# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A UFC fight-outcome predictor: an XGBoost + LightGBM ensemble trained on engineered fighter/fight
history, served through a small Streamlit app and a weekly predictions job. `ufc_prediction_claude.ipynb`
is the single source of truth for the modeling pipeline. (Two superseded notebooks,
`ufc_prediction.ipynb` and `ufc_analysis.ipynb`, were removed in the Aug 2026 cleanup — recover from
git history if ever needed.)

Raw data (`raw_fight_data.csv`, `raw_fighter_details.csv`) is produced by a separate sibling scraper
project at `../UFC-Predictions` (its own `src/createdata/` pipeline) and copied into this repo — this
repo does not scrape data itself. Since Aug 2026 the fighter CSV includes a Wikidata-sourced
`Country` column (citizenship; `;`-joined for dual citizens) feeding the home-crowd features —
CSVs from before that change still run, the home-crowd features just come out all-NaN.

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

# pipeline-shape / data-leak guards (pytest)
.venv/bin/pytest test_pipeline_logic.py -v

# predict a fight card with betting odds (used by the weekly Routine; writes
# predictions_output.md with a value-bet $100 Kelly split when odds are given;
# --event-country feeds the home-crowd features, omit if unknown)
.venv/bin/python send_weekly_predictions.py --fights-json card.json --event-title "UFC ..." \
    --event-country USA
```

There is no lint/build config; tests are `test_predict.py` and `test_pipeline_logic.py`.

## Architecture

**Notebook pipeline stages** (in execution order — cell order in the `.ipynb` is meaningful and has
been hand-edited via direct JSON manipulation rather than the Jupyter UI, see gotcha below):

1. Load raw CSVs → clean/normalize columns → merge fighter details onto fight rows by
   lowercased/trimmed name.
2. Feature engineering, each producing `r_*`/`b_*` paired columns computed from **prior fights only**
   (no lookahead): career avg/median stats, win/loss streaks, fight frequency/layoff, matchup diffs,
   head-to-head record, KO/submission finish rates, first-round wins, average time-into-the-fight
   for wins/losses, a shared `rules_era` ordinal (pre-unified / unified-2001 / 2017-revision — the
   one non-paired feature; pinned to the current era at predict time in both the notebook's
   prediction cell and `predict.py`), home-crowd flags (fighter's Wikidata citizenship vs. the
   event location's country — supplied per-prediction via `event_country`, never inherited from a
   fighter's last fight row), judge-scorecard history (prior-decision margin/closeness/dominance from
   the vendored `data/SCORECARDS.csv`, UFC-DataLab, MIT — NaN outside its mid-2020→late-2024
   coverage), and Elo rating (the one feature computed via a
   sequential chronological loop rather than a vectorised cumsum, since each fight's rating depends
   on both fighters' evolving state). Full definitions with math + plain explanations:
   `docs/METHODOLOGY.md` and `docs/DATA_DICTIONARY.md`; run history: `EXPERIMENTS.md`.
3. Target/feature selection → correlation check → **rolling-window grid search** to pick how much
   trailing history to train on → **Optuna** hyperparameter search evaluated with the same
   walk-forward CV scheme (never a plain train/test split).
4. Final holdout split: validation slice (threshold/blend tuning) + test slice (scored once).
5. Ensemble: top-3 Optuna trials + one LightGBM model, blended at whichever mixing weight scores best
   on validation.
6. Decision layer, stability checks, and export — see gotchas below for why several of these exist.

**Weekly automation**: one claude.ai Routine (Thursday 13:00 UTC, self-bound session) retrains via
`scripts/weekly_pipeline.sh` (scrape → CPU retrain → push master), then predicts the upcoming card
with bookmaker odds via `send_weekly_predictions.py` and pushes the result table to the
`weekly-predictions-log` branch — that push is the delivery mechanism; there is deliberately no email
path (SMTP is unreachable from the cloud environment, and a Gmail app password was leaked into git
history doing it the old way — revoke-and-avoid, don't reintroduce). Betting maths lives in
`predict.py:kelly_edge` and is shared by the weekly job and the app's optional odds inputs.

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
- **`last_row()`** (`predict.py`) must reorient a fighter's most recent fight row when they fought in
  the blue corner last time — otherwise the `r_`-prefixed columns silently describe their opponent
  instead of them. This was a real bug, only caught by `test_predict.py`'s corner-swap symmetry check.
- **Serving reads every feature through `own_value()`/`diff_pairs`, never raw `b_*` columns.** A
  reoriented last-fight row's `b_*` side is by construction the fighter's LAST OPPONENT; reading it
  directly once served ~half the feature vector from the wrong fighter, and substring-matching diff
  sources zero-filled all 25 `avg_*`/`med_*` diffs (EXPERIMENTS.md entry 0). `build_features` in
  `predict.py` is the single serving implementation — the notebook's prediction cell imports it;
  never re-inline a copy. The corner-swap symmetry test cannot catch this class of bug (its fighters
  last fought each other, so contamination self-cancels); the content-based serving test in
  `test_pipeline_logic.py` (never-met pair, every feature checked against the fighter's own history)
  is the guard.
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
- **XGBoost device is `DEVICE`, probed once at startup** (settings cell: a tiny cuda fit in a
  subprocess with a timeout, because a broken driver — the desktop's current state — can HANG CUDA
  init rather than fail it). All four training sites (`create_xgb_model()`, the Optuna objective,
  the top-3 refits, the calibration OOF refits) reference `DEVICE`; never hardcode a device at one
  site. The laptop's eGPU joins tuning via `scripts/shared_study_worker.py` (dispatched over ssh;
  runs the same probe on its own device) — requires `OPTUNA_STORAGE_URL` and
  `OPTUNA_WORKER_STORAGE_URL` in the environment; credentials are never committed. LightGBM stays
  CPU-only (a GPU build isn't worth the packaging).

## Experiment protocol (mandatory for any feature or algorithm change)

- **Retrain and log every change.** Any change to features or the algorithm gets a full pipeline run
  (Restart + Run All) and an entry in `EXPERIMENTS.md` — window, validation/test accuracy + AUC with
  the CLT interval, monthly-batch stats, and the paired McNemar comparison against the snapshotted
  baseline (`cp ensemble.joblib ensemble_baseline.joblib` BEFORE retraining). One variable per run;
  rejected changes are fully reverted, never left in because they "don't hurt".
- **The profitability metric**: each entry records value-bet ROI of the model's pooled-OOF
  predictions against historical closing odds (`scripts/odds_backtest.py`; odds DB restored locally
  from the mma-ai dump, never committed — unlicensed upstream). The pooled-OOF McNemar gates
  accuracy; when it's a statistical tie, profitability on common fights breaks the tie.
- **The $100 replay metric**: each entry also records how the new model would have used the $100
  bankroll on the last UFC event versus what was actually logged. Always score the LOGGED pre-event
  predictions from the `weekly-predictions-log` branch — never re-predict a past event through
  current history (its outcome is already inside `head_to_head` and the fighters' last rows). The
  weekly job commits `card.json` next to `predictions_output.md` to make this mechanical.
- **Docs move with the code.** `docs/METHODOLOGY.md` and `docs/DATA_DICTIONARY.md` are updated in the
  same commit as any change to features, data, or algorithm — each concept explained mathematically
  first, then in plain terms with a worked example (write for a data-science undergrad).

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
