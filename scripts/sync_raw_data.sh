#!/usr/bin/env bash
# Runs the UFC-Predictions scraper and copies its raw output into this repo
# under the filenames the notebook expects (see CLAUDE.md's "What this repo is").
# Location-independent: paths derive from this script's own location, with the
# scraper expected as a sibling checkout (../UFC-Predictions) -- the Python
# folder has moved homes before and hardcoded paths broke.
set -euo pipefail

TARGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRAPER_DIR="$(cd "$TARGET_DIR/.." && pwd)/UFC-Predictions"

[ -d "$SCRAPER_DIR" ] || {
  echo "Scraper not found at $SCRAPER_DIR -- clone it there first:"
  echo "  git clone https://github.com/Michael-Alizzi/UFC-Predictions.git \"$SCRAPER_DIR\""
  exit 1
}

cd "$SCRAPER_DIR"
# exFAT/FAT drives can't hold the symlink a Linux venv requires -- fall back
# to a venv on the internal drive. Moved venvs are rebuilt (absolute paths).
VENV=.venv
if ln -s . .symlink_test 2>/dev/null; then
  rm -f .symlink_test
else
  VENV="$HOME/.cache/ufc_scraper_venv"
  echo "scraper drive can't hold symlinks (exFAT?) -- venv lives at $VENV"
fi
if ! "$VENV/bin/python" -c '' 2>/dev/null; then
  rm -rf "$VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r requirements.txt
fi
"$VENV/bin/python" -m src.create_ufc_data

cp "$SCRAPER_DIR/data/raw_total_fight_data.csv" "$TARGET_DIR/raw_fight_data.csv"
cp "$SCRAPER_DIR/data/raw_fighter_details.csv" "$TARGET_DIR/raw_fighter_details.csv"

echo "Synced raw data into $TARGET_DIR. Re-run ufc_prediction_claude.ipynb to retrain on it."
