#!/usr/bin/env bash
# One-command runner for the two queued experiment retrains (EXPERIMENTS.md
# entries 1-2). Run from the repo root on the desktop and leave it alone:
#
#   bash scripts/run_experiments.sh
#
# Does, in order: snapshot the current model as baseline -> retrain at the
# baseline-v2 commit (window search + Optuna; desktop GPU via the startup
# probe, laptop eGPU via the notebook's ssh dispatch) -> auto-log entry 1 ->
# re-snapshot -> pin the chosen window -> retrain at branch head (scorecard
# features, vs. the v2 baseline's pooled OOF) -> auto-log entry 2 -> run the
# test suite -> commit artifacts + entries -> push. Multi-hour total.
set -euo pipefail

BASELINE_V2_COMMIT=5cb0a9b
BRANCH=claude/ufc-prediction-features-at7ht2
NB=ufc_prediction_claude.ipynb
RUNDIR=.experiment_runs   # gitignored; keeps run-1 artifacts for possible revert

# ── preconditions ──
# FAT-family filesystems (exFAT USB drives) report every file's mode as
# changed; set this before the dirty-tree check or it always trips there.
git config core.filemode false
[ -f raw_fight_data.csv ] && [ -f raw_fighter_details.csv ] || {
  echo "raw CSVs missing -- run scripts/sync_raw_data.sh once first"; exit 1; }
git diff --quiet && git diff --cached --quiet || {
  echo "working tree dirty -- commit or stash first"; exit 1; }
git rev-parse --verify -q "$BASELINE_V2_COMMIT" >/dev/null || {
  echo "commit $BASELINE_V2_COMMIT not found -- git fetch first"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || {
  echo "check out $BRANCH first"; exit 1; }

if [ -z "${OPTUNA_STORAGE_URL:-}" ] || [ -z "${OPTUNA_WORKER_STORAGE_URL:-}" ]; then
  if [ "${1:-}" != "--allow-no-laptop" ]; then
    echo "OPTUNA_STORAGE_URL / OPTUNA_WORKER_STORAGE_URL are not set, so the"
    echo "laptop eGPU cannot join the shared study. Export them (CLAUDE.md ->"
    echo "GPU gotcha) and re-run, or accept desktop-only tuning with:"
    echo "    bash scripts/run_experiments.sh --allow-no-laptop"
    exit 1
  fi
  echo "WARNING: running desktop-only (no laptop worker)."
fi

# A moved repo carries a broken venv (venvs bake absolute paths), and
# exFAT/FAT USB drives can't hold symlinks -- rebuild with copies if needed.
if ! .venv/bin/python -c '' 2>/dev/null; then
  rm -rf .venv
  python3 -m venv .venv 2>/dev/null || python3 -m venv --copies .venv
fi
.venv/bin/pip install -q -r requirements.txt

# ── GPU status up front, so a still-broken driver is visible immediately ──
nvidia-smi -L 2>/dev/null || echo "(nvidia-smi unavailable)"
.venv/bin/python - <<'PY'
import subprocess, sys
code = ("import numpy as np; from xgboost import XGBClassifier; "
        "XGBClassifier(n_estimators=2, tree_method='hist', device='cuda').fit("
        "np.array([[0.],[1.],[0.],[1.]]), [0,1,0,1])")
try:
    ok = subprocess.run([sys.executable, "-c", code],
                        capture_output=True, timeout=60).returncode == 0
except subprocess.TimeoutExpired:
    ok = False
print("desktop CUDA probe:", "PASS -- XGBoost trains on GPU" if ok
      else "FAIL/timeout -- XGBoost trains on CPU (driver still broken?)")
PY

mkdir -p "$RUNDIR"

retrain () {  # retrain <slug> <entry title>
  echo "=== retrain $1 started $(date) ==="
  .venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.timeout=-1 "$NB"
  .venv/bin/python scripts/log_run_metrics.py log "$NB" "$2" | tee "$RUNDIR/$1.log"
  cp ensemble.joblib "$RUNDIR/$1.ensemble.joblib"
  cp fighter_history.parquet "$RUNDIR/$1.fighter_history.parquet"
}

# ── run 1: baseline v2 (pre-scorecards) vs the Jul-28 model ──
cp ensemble.joblib ensemble_baseline.joblib
git checkout "$BASELINE_V2_COMMIT" -- "$NB"
retrain run1-baseline-v2 "1. Baseline v2 -- leak-free window search, OOF gate"

# ── run 2: scorecard features vs baseline v2, window pinned from run 1 ──
cp ensemble.joblib ensemble_baseline.joblib
git checkout "$BRANCH" -- "$NB"
WINDOW=$(grep -oP 'PARSED_WINDOW=\K.*' "$RUNDIR/run1-baseline-v2.log" || true)
if [ -n "$WINDOW" ]; then
  .venv/bin/python scripts/log_run_metrics.py pin "$NB" ${WINDOW/,/ }
else
  echo "WARNING: run-1 window not parsed -- run 2 will re-search (slower, still valid)"
fi
retrain run2-scorecards "2. Judge-scorecard features"

# ── verify + ship ──
.venv/bin/python -m pytest -q test_pipeline_logic.py test_predict.py

git add "$NB" ensemble.joblib fighter_history.parquet EXPERIMENTS.md
git commit -m "Retrain runs 1-2: baseline v2 + scorecard experiment (auto-logged in EXPERIMENTS.md)"
git push -u origin "$BRANCH"

echo "=== done $(date). Read the two entries in EXPERIMENTS.md; the"
echo "Pooled-OOF McNemar line in entry 2 is the accept/revert decision."
echo "Run-1 artifacts kept in $RUNDIR/ in case entry 2 is reverted."
