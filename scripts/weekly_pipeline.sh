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

python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt

# device="cpu" throughout + the Optuna cell's Postgres->in-process fallback
# (see ufc_prediction_claude.ipynb) make this safe to run GPU-less.
.venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 ufc_prediction_claude.ipynb

echo "Retrain complete: ensemble.joblib + fighter_history.parquet refreshed."
