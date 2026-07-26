#!/usr/bin/env bash
# Runs the UFC-Predictions scraper and copies its raw output into this repo
# under the filenames the notebook expects (see CLAUDE.md's "What this repo is").
set -euo pipefail

SCRAPER_DIR="/home/michael/Documents/Python/UFC-Predictions"
TARGET_DIR="/home/michael/Documents/Python/my_ufc_prediction"

cd "$SCRAPER_DIR"
"$SCRAPER_DIR/.venv/bin/python" -m src.create_ufc_data

cp "$SCRAPER_DIR/data/raw_total_fight_data.csv" "$TARGET_DIR/raw_fight_data.csv"
cp "$SCRAPER_DIR/data/raw_fighter_details.csv" "$TARGET_DIR/raw_fighter_details.csv"

echo "Synced raw data into $TARGET_DIR. Re-run ufc_prediction_claude.ipynb to retrain on it."
