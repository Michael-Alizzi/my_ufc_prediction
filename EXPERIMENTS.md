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
Profitability (OOF vs closing odds, scripts/odds_backtest.py): flat ROI ...,
    kelly ROI ..., close-vs-onesided segment ROI ... (n bets ...);
    market favourite wins ...% on the same fights.
$100 replay (last event): scored the LOGGED pre-event predictions from
    weekly-predictions-log against results: old model $... -> $... return.
    New model's stakes on the same card: <table or one-liner>.
Decision: ACCEPTED / REVERTED — why.
```

**Profitability rule:** betting is the model's end use, so each entry also
records value-bet profitability: both models' pooled-OOF predictions scored
against historical closing odds (BestFightOdds via the locally-restored
mma-ai dump — unlicensed upstream, so the odds DB lives ONLY on the desktop
and only aggregate numbers appear here). `scripts/odds_backtest.py` reports
flat and Kelly ROI, the "model-close / bookies-one-sided" segment (the
strategy actually bet), and the market-favourite baseline. Role: the
pooled-OOF McNemar remains the accuracy gate; **when that gate is a
statistical tie, the profitability comparison on common fights breaks the
tie** — equal accuracy does not mean equal betting value.

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

Both queued changes are on the branch; keep the comparisons one-variable by
running each retrain at its commit. **One command does the whole protocol**
(snapshots, both retrains, window pinning, auto-logged entries, tests,
commit + push) — run it from the repo root on the desktop and walk away:

```bash
bash scripts/run_experiments.sh
```

It refuses to start without the Optuna env vars (so the laptop eGPU joins);
override with `--allow-no-laptop` for desktop-only tuning. Run-1 artifacts
are stashed in `.experiment_runs/` in case entry 2 gets reverted.


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

---

### 1. Baseline v2 -- leak-free window search, OOF gate        2026-08-03, notebook at ee3ad47
Auto-logged from the executed notebook's output cells:

```
XGBoost device: cuda
Dropped 956 duplicate fight rows (8310 remain)
Dropped 0 med_* duplicates of avg_* (r>0.95 both corners, pre-holdout); 229 columns remain
Best window: 72 months train / 6 months test
Training period: 2020-01-18 → 2026-01-18
Laptop eGPU joined shared study 'xgb_tuning_20260803_125404' (combined cap: 100 trials)...
Shared study 'xgb_tuning_20260803_125404' complete: 101 trials total (desktop + laptop combined). Best AUC: 0.6581
Validation: 120 fights (2026-01-18 → 2026-04-18)
Test:       110 fights (2026-04-18 → 2026-07-18)
Pooled OOF for export: 7869 fights
diff_pairs verified for 46 diff features
Pooled test accuracy: 0.609  (n=110)
95% CI (CLT):        [0.518, 0.700]
Batch accuracy: 0.563 +/- 0.244 over 4 monthly batches
Baseline accuracy: 0.600
This run accuracy: 0.609
New fixes 1 fights baseline got wrong
New breaks 0 fights baseline got right
Test-set McNemar p-value: 1.0000 (sanity check only)
Prediction: Ilia Topuria wins
Confidence: 64.37% that Ilia Topuria wins
```

$100 replay (last event): (fill in from weekly-predictions-log)
Decision: ACCEPTED — hygiene release as pre-registered (1 fix / 0 breaks vs
the Jul-28 model on the test set); becomes the reference baseline. First
artifact carrying oof/diff_pairs/train_end.

---

### 2. Judge-scorecard features        2026-08-04, notebook at ee3ad47
Auto-logged from the executed notebook's output cells:

```
XGBoost device: cuda
Dropped 956 duplicate fight rows (8310 remain)
Scorecards joined to 1000 decisions (25.4% of all decisions; coverage is mid-2020..late-2024 by data availability); winner agreement 99.8%
Dropped 0 med_* duplicates of avg_* (r>0.95 both corners, pre-holdout); 238 columns remain
Window pinned at (72, 6) -- skipping grid search
Best window: 72 months train / 6 months test
Training period: 2020-01-18 → 2026-01-18
Laptop eGPU joined shared study 'xgb_tuning_20260803_224925' (combined cap: 100 trials)...
Shared study 'xgb_tuning_20260803_224925' complete: 101 trials total (desktop + laptop combined). Best AUC: 0.6581
Validation: 120 fights (2026-01-18 → 2026-04-18)
Test:       110 fights (2026-04-18 → 2026-07-18)
Pooled OOF for export: 7869 fights
diff_pairs verified for 49 diff features
Pooled test accuracy: 0.609  (n=110)
95% CI (CLT):        [0.518, 0.700]
Batch accuracy: 0.538 +/- 0.306 over 4 monthly batches
Baseline accuracy: 0.609
This run accuracy: 0.609
New fixes 1 fights baseline got wrong
New breaks 1 fights baseline got right
Test-set McNemar p-value: 1.0000 (sanity check only)
Pooled-OOF comparison on 7869 aligned fights (baseline acc 0.6171 vs this run 0.6176)
OOF fixes 101 / breaks 97; McNemar p-value: 0.8312  <-- primary gate
No statistically significant difference — could be noise
Prediction: Ilia Topuria wins
Confidence: 64.20% that Ilia Topuria wins
```

$100 replay (last event): (fill in from weekly-predictions-log)
Profitability: PENDING — odds backtest queued (accuracy gate was a precise
null: OOF 0.6171 vs 0.6176, p=0.8312 on 7,869 fights).
Decision: PENDING the profitability tie-break — if scorecards don't win it,
REVERT per protocol (static coverage only shrinks going forward; a
scorecards-v2 sourced from ufcstats' own judge totals, ~4x coverage and
weekly-refreshed, is the queued successor idea).
