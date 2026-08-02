# Experiment Log

Every feature or algorithm change gets exactly one entry here, filled in
after the full pipeline run that measured it. Protocol (also in CLAUDE.md):

1. **One variable per run.** A change ships alone; its entry names the single
   thing that changed.
2. **Snapshot the baseline first**: `cp ensemble.joblib ensemble_baseline.joblib`
   before retraining, so the notebook's Paired Comparison cell has something
   to compare against.
3. **Run the full pipeline** (Restart + Run All / `nbconvert`), then record
   the metrics below from the notebook's output cells.
4. **Decide**: the primary gate is the pooled-OOF McNemar (~6,000 fights);
   the 110-fight test set (95% CI ≈ ±9 points) is a sanity check only.
   Rejected changes are **fully reverted** — nothing stays in because it
   "doesn't hurt".
5. **Update the docs** (`docs/METHODOLOGY.md`, `docs/DATA_DICTIONARY.md`)
   in the same commit as any accepted change.

## Entry template

```
### <n>. <change title>            <date>, commit <sha>
Change (one variable): ...
Window: <train>/<test> months (pinned | re-searched)
Validation: acc ..., AUC ...
Test:       acc ... (n=..., 95% CI [..., ...]), AUC ...
Monthly batches: ... ± ... over ... months
Paired vs baseline: pooled-OOF McNemar p=... (fixes ..., breaks ...);
                    test-set McNemar p=...
$100 replay (last event): scored the LOGGED pre-event predictions from
    weekly-predictions-log against results: old model $... -> $... return.
    New model's stakes on the same card: <table or one-liner>.
Decision: ACCEPTED / REVERTED — why.
```

**$100 replay rule:** always score the *logged* pre-event predictions
(`weekly-predictions-log` branch) — never re-predict a past event through
current history, because `head_to_head` and the fighters' last-row features
already include that event's outcome (self-inclusion leak). The weekly job
commits `card.json` (with odds) alongside `predictions_output.md` so the new
model's stakes on the same card are reproducible mechanically.

---

### 0. Serving corruption fixed — model unchanged        2026-08-02
Change: `predict.build_features` rewritten. Previously ~half the serving
feature vector came from the wrong fighter: `b_*` features were read off the
blue fighter's reoriented last row (= their **last opponent's** stats),
`avg_b_*`/`med_b_*` came from the *red* fighter's last opponent, all 25
`avg_*`/`med_*` diffs were silently zero-filled, and the remaining diffs
mixed red-own with blue's-last-opponent values. Verified example: predicting
Makhachev–Holloway served Holloway's height as 175cm (McGregor's) and his
layoff as 1827 days (McGregor's).
Model artifacts: **unchanged** (notebook training/holdout matrices were
always built correctly — only the app/weekly-card serving path was wrong).
Every served prediction changes from this date; logged predictions before it
were produced by the corrupted path and should be read accordingly.
Gate: content-based serving test added (never-met pair, every feature checked
against the fighter's own history); no retrain required.
Decision: ACCEPTED (bug fix).

---

## Queued (implemented, awaiting user retrains — fill each in from the run)

### 1. Baseline v2 — leak-free window search, OOF gate        (retrain #1)
Change: window search restricted to pre-holdout data; HOLDOUT_START pinned
at latest−6mo (reproduces the current 120/110 split, so the Jul-28 baseline
stays comparable); LightGBM subsample activated (subsample_freq); DEVICE
auto-probe. Window re-searched this once — pin `BEST_WINDOW` to the chosen
pair afterwards.
Expectation (written before the run): hygiene, not a metric mover — the old
leak touched ~1 fold of the winning combo. This run's export becomes the
first artifact carrying `oof`/`diff_pairs`/`train_end`; snapshot it as the
baseline for everything below.

### 2. Judge-scorecard features        (retrain #2)
Change: + r_/b_avg_dec_margin, close_dec_rate, dominant_dec_rate (+diffs).
Expectation (written before the run): SMALL effect. Coverage is ~1,000
scored decisions (mid-2020→late-2024, frozen thereafter — static vendored
file); holdout fights are 2026, where career aggregates carry late-2024
values for established fighters and NaN for newcomers. Gate on pooled OOF;
revert fully if it loses.

### 3–6. Queued experiments (one retrain each, in order)
decay (wall-clock EWM halflife replaces fight-count) → shrinkage
(finish rates toward weight-class priors) → absorbed/defensive stats →
opponent-adjusted performance. Implemented one at a time only after the
previous entry is decided; specs in docs/METHODOLOGY.md as they land.

### 7. Historical odds backtest (gated)
mma-ai's BestFightOdds dump: ~2.5 GB on Hugging Face, repo carries NO
license → download privately on your own machine only; nothing from it gets
committed here. Deliverable: accuracy vs closing line + $100 Kelly ROI over
history, aggregated numbers only in this log.
