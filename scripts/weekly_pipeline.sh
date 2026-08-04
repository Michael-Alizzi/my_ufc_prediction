#!/usr/bin/env bash
# Cloud counterpart to sync_raw_data.sh: clones UFC-Predictions fresh (no local
# sibling checkout to rely on), scrapes, renames raw files into this repo, then
# retrains headlessly. Run from the my_ufc_prediction repo root.
set -euo pipefail

SCRAPER_DIR="../UFC-Predictions"
if [ ! -d "$SCRAPER_DIR" ]; then
  git clone --depth 1 https://github.com/Michael-Alizzi/UFC-Predictions.git "$SCRAPER_DIR"
fi

python3 -m venv "$SCRAPER_DIR/.venv" 2>/dev/null || true
"$SCRAPER_DIR/.venv/bin/pip" install -q -r "$SCRAPER_DIR/requirements.txt"
(cd "$SCRAPER_DIR" && ./.venv/bin/python -m src.create_ufc_data)

cp "$SCRAPER_DIR/data/raw_total_fight_data.csv" raw_fight_data.csv
cp "$SCRAPER_DIR/data/raw_fighter_details.csv" raw_fighter_details.csv

# The raw CSVs are tracked in git, so "did anything change since the last
# retrain" is just a diff against the committed copies. If the fresh scrape
# matches them, the multi-hour retrain would only reproduce the committed
# artifacts -- skip it; a later week's run picks up new data.
if git diff --quiet -- raw_fight_data.csv raw_fighter_details.csv; then
  echo "No new fight data since last retrain; skipping retrain."
  exit 0
fi

python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt

# Headless-safe: Optuna storage is env-gated (unset here -> in-process),
# the laptop dispatch, baseline comparison and prediction demo cells all
# skip cleanly when their inputs are missing, and raw CSV paths are
# repo-relative.
.venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 ufc_prediction_claude.ipynb

# Fail the run loudly if the fresh artifacts break the serving contract
.venv/bin/python -m pytest -q test_pipeline_logic.py test_predict.py

echo "Retrain complete: ensemble.joblib + fighter_history.parquet refreshed."
echo "Commit the refreshed CSVs together with the artifacts (they are tracked)."
