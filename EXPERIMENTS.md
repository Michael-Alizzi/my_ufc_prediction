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

## Queued (next experiments, in order)

**The bar is the market, not a coin flip** (see CLAUDE.md → What this repo
is): closing favourites win 66.3% / log-loss 0.6089 on the 5,786 backtested
fights vs the model's 61.2% / 0.642. An experiment that improves accuracy
without closing that gap hasn't moved the needle that matters.

**Compute note (2026-08-04):** retrains now run on **cloud CPU** (the same
path as the weekly pipeline) rather than the desktop/laptop GPUs — the
DEVICE probe falls back to cpu automatically; expect longer wall-clock. The
per-run protocol is unchanged: snapshot baseline → one variable → full run →
auto-log (`scripts/log_run_metrics.py`) → pooled-OOF McNemar gate with the
profitability tie-break → full revert on rejection. The odds backtest still
runs on the desktop only (that's where the odds DB lives).

### 3. Beat-the-market betting rule        (next up — no retrain, decision layer)
Change: use the market as an input to bet selection instead of betting
against it. The current value-bet rule stakes wherever model probability
beats implied probability — which concentrates bets exactly where the model
disagrees with a better-calibrated market (84% underdogs, −9.5% ROI in the
close-vs-onesided segment). Candidate replacement: bet only when the model
agrees with the market's direction AND its edge over the implied probability
exceeds the vig (ride the market selectively, never fade it); compare
against a shrunk blend (model proba shrunk toward the vig-free implied
probability) as the staking input. Evaluated on the same OOF-with-odds
fights via `scripts/odds_backtest.py` on the desktop — model artifacts
unchanged, so no McNemar gate; the gate IS the ROI comparison against the
current rule on identical fights.
Expectation (written before the run): flat/Kelly ROI improves mainly by
*not betting* the worst segment; total bet count drops sharply. If no
positive-ROI rule exists at closing odds, that finding gets recorded
honestly — the model then needs to get better, not the staking cleverer.

### 4–7. Feature/algorithm queue (one CPU retrain each, in order)
decay (wall-clock EWM halflife replaces fight-count) → shrinkage
(finish rates toward weight-class priors) → absorbed/defensive stats →
opponent-adjusted performance. Implemented one at a time only after the
previous entry is decided; specs in docs/METHODOLOGY.md as they land. Each
entry records the market-baseline comparison, not just the paired McNemar.

### Later: scorecards v2 (successor to the reverted entry 2)
Same three decision-margin features, sourced from ufcstats' own judge
totals instead of the static UFC-DataLab CSV (~4× coverage, refreshed
weekly by the scraper). Worth a retrain only after the queue above settles.

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

Profitability (OOF vs closing odds, scripts/odds_backtest.py; 5786/7869 OOF
fights matched to odds, 74% coverage): flat ROI -0.5% (5368 bets, hit
39.0%), kelly ROI +0.9%, close-vs-onesided segment ROI -9.5% (1637 bets, hit
25.5%); market favourite wins 66.3% on the same fights (market log-loss
0.6089 vs this model's 0.6422).

$100 replay (last event, UFC Belgrade — Medić vs Rodríguez): the LOGGED
(deployed-model) predictions returned $100 → $49 (net −$51). Baseline v2
re-weighted the same three losing sides and found no value on Musayev — the
one logged bet that paid off — so it returns $100 → $0 (net −$100).
Caveat: that card predates the commit-card.json rule, so odds were
reconstructed from the logged markdown (bet sides only); 3 of 7 fights had
no odds and no stake from any model (none were bet originally either).
One-card sample — noise-level evidence, recorded for the protocol not the
decision.
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

$100 replay (last event, UFC Belgrade — Medić vs Rodríguez): identical
behaviour to baseline v2 — same three losing sides (re-weighted), no value
found on Musayev: $100 → $0 (net −$100) vs the deployed model's −$51. Since
baseline v2 *without* scorecards made the same bets, the scorecard features
are not the differentiator on this card; n=1, noise-level evidence either
way (same caveats as entry 1).
Profitability (OOF vs closing odds, scripts/odds_backtest.py; 5786/7869 OOF
fights matched to odds, 74% coverage): flat ROI -0.8% (5378 bets, hit
38.7%), kelly ROI +0.6%, close-vs-onesided segment ROI -9.8% (1728 bets, hit
25.5%); market favourite wins 66.3% on the same fights (market log-loss
0.6089 vs this model's 0.6431). Baseline v2 leads on every metric here
(higher flat ROI, higher kelly ROI, better segment ROI, better log-loss) —
tie-break goes against scorecards.
Decision: REVERTED — pooled-OOF McNemar was a statistical tie (p=0.8312);
the profitability tie-break favors baseline v2 on every metric, and the
$100 Belgrade replay showed no advantage either. Static coverage (mid-2020
→late-2024, frozen) only shrinks going forward; a scorecards-v2 sourced from
ufcstats' own judge totals (~4x coverage, weekly-refreshed) is the queued
successor idea.
