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
Market comparison (OOF fights matched to closing odds, scripts/odds_backtest.py):
    accuracy:     model ...% vs market favourite ...%
    prob quality: model log-loss ... vs market log-loss ...
    dollar value: flat ROI ...%, kelly ROI ...%,
                  close-vs-onesided segment ROI ...% (n bets ...)
$100 replay (last event): scored the LOGGED pre-event predictions from
    weekly-predictions-log against results: old model $... -> $... return.
    New model's stakes on the same card: <table or one-liner>.
Decision: ACCEPTED / REVERTED — why.
```

**Market-comparison rule:** beating the market is the point of the project
(CLAUDE.md → What this repo is), so every entry records three metrics
against it, all from `scripts/odds_backtest.py` on the OOF fights matched
to historical closing odds (BestFightOdds via the locally-restored mma-ai
dump — unlicensed upstream, so the odds DB lives ONLY on the desktop and
only aggregate numbers appear here):
1. **Accuracy vs the market** — model win-pick accuracy vs how often the
   closing favourite wins on the same fights.
2. **Probability quality** — model log-loss vs the market's log-loss from
   vig-free implied probabilities; the gap ≈ expected log-bankroll loss per
   full-Kelly bet before vig, so this is the metric that must close.
3. **Dollar value** — flat and Kelly ROI of the value-bet rule, plus the
   "model-close / bookies-one-sided" segment (the strategy actually bet).
Role: the pooled-OOF McNemar remains the accuracy gate for accepting a
change; **when that gate is a statistical tie, the market comparison on
common fights breaks the tie** — equal accuracy does not mean equal
betting value.

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

### 4–5. Feature queue        (one CPU retrain each, in order; #4 next up)
**#4 shrinkage** (finish rates toward weight-class priors) →
**#5 absorbed/defensive stats**. Implemented one at a time only after the
previous entry is decided; specs land in docs/METHODOLOGY.md with each.
Each entry records the full market comparison, not just the paired McNemar.
(#3 decay: DECIDED without a retrain — see entry 3 at the bottom of this
log; the notes immediately below are the investigation's history.)

Expectation for #4 (written before the run, 2026-08-04): the 4 finish-rate
stats (`ko_win_rate`, `sub_win_rate`, `ko_loss_rate`, `sub_loss_rate`, both
corners + diffs) are REPLACED by empirical-Bayes shrunk versions —
`(K·p_wc + count) / (K + n)` with K=5 pseudo-fights at the weight class's
pre-holdout base rate `p_wc`; debuts get the pure class prior instead of
NaN. Mechanism: raw rates scream on tiny samples (1 KO in 2 fights reads
"50% finisher"), and trees split on those loud lies; shrinkage silences
exactly the small-n rows while leaving veterans' rates almost untouched.
Expect a small positive effect concentrated on fights involving
short-record fighters; possible null if the trees were already routing
around noisy rates via n-correlated features. Gate: pooled-OOF McNemar vs
baseline v2, market comparison recorded, full revert if it loses. Same
column names (values change, schema doesn't), so mirroring/selection/
serving are untouched.

Expectation for #3 (written before the run): `avg_*` halflife becomes 3
years of wall-clock time instead of 5 fights. The two disagree mainly for
fighters returning from long layoffs (their stale form now fades properly);
active fighters' averages barely move. Expect a small effect concentrated
on comeback fights; gate on pooled-OOF McNemar vs baseline v2 with the
market comparison recorded, full revert if it loses.

**Halflife selection (2026-08-04, notebook cells 14-15, desktop, pre-gating-retrain):**
the 3-year figure above was originally a round-number guess ("3y ≈ 5 fights
at a typical cadence", not tuned). Replaced with a data-driven pick plus an
independent cross-check, both run on pre-holdout data only:

- **CV grid search** (`avg_*_diff` feature block alone, default XGBoost,
  pinned 72/6-month rolling window — the same harness as the window search,
  not a full pipeline re-run per candidate): grid `[1, 1.5, 2, 3, 4, 5, 7,
  10, 15]` years plus a flat/expanding-mean (no-decay) reference. AUC
  clustered tightly across every candidate (0.5284-0.5375) — **3.0y won
  narrowly** (0.5359) but the **no-decay reference beat every single
  numeric halflife** (0.5375). Extending the grid to 7/10/15y found nothing
  better than 3.0y (7y was in fact the worst numeric candidate). Read
  honestly: halflife choice barely moves this feature block's own CV
  signal at all; 3.0y is "best of a flat curve," not a confident optimum.
- **Autocorrelation cross-check** (independent of the CV metric entirely —
  estimates how long raw per-fight stats stay correlated with a fighter's
  own future performance, straight from the data): every fighter's fight
  pairs, z-scored **within weight class** (a first pass that z-scored
  globally conflated division identity with persistence and was
  discarded), correlation of z-scores bucketed by gap and fit to
  `corr(Δt) = a + b·0.5^(Δt/h)` (floor `a` = permanent identity/division/
  physique the model gets elsewhere; `h` = the form halflife that's
  actually comparable to `AVG_HALFLIFE`), weighted least squares via
  `scipy.optimize.curve_fit`. Result: pooled `h = 9.62y`, but **the fit is
  degenerate** — `a` lands pinned at its 0 lower bound for the pooled fit
  and 3 of 4 per-stat fits (only `sig_str_frac` identifies a real floor:
  a=0.105, h=1.23y). With only 6 years of gap range, the fit can't
  separate "small floor + fast decay" from "no floor + slow decay" — both
  explain the observed correlation curve equally well, so `h=9.62y`
  shouldn't be read as a confirmed number.
- **Net read**: neither of the two clean outcomes anticipated going in
  (corrected h near 2-4y confirming 3y, or h≫5y *with* a grid lift at long
  halflives confirming a longer pick) actually happened — h came out ≫5y
  pooled, but the grid never lifted at long halflives, and the h estimate
  itself is degenerate. This is genuinely ambiguous evidence, not a
  confirmation or a refutation. Per protocol the CV grid still governs:
  **AVG_HALFLIFE_YEARS pinned at 3** (no longer value beat it). Additional
  caveat on every fitted-h number above: survivorship bias — only
  long-career fighters contribute long-gap pairs, so `h` is inflated
  somewhat regardless of the floor correction.
- Upgrade path, if this is ever worth resolving properly: the isolated
  CV proxy and the identifiability-limited autocorrelation fit are both
  cheap diagnostics, not a full pipeline evaluation — the real test is
  whether the gating retrain's pooled-OOF McNemar (below) prefers a
  different halflife once threaded through the complete feature set.

### 6. Opponent-adjusted performance        (CPU retrain; builds on #5)
Per-fight z-scores vs the opponent's prior allowed averages, career-
aggregated — needs #5's absorbed/defensive stats as inputs.

### 7. Beat-the-market betting rule        (last — no retrain, decision layer)
Change: use the market as an input to bet selection instead of betting
against it. The current value-bet rule stakes wherever model probability
beats implied probability — which concentrates bets exactly where the model
disagrees with a better-calibrated market (84% underdogs, −9.5% ROI in the
close-vs-onesided segment). Candidate replacement: bet only when the model
agrees with the market's direction AND its edge over the implied probability
exceeds the vig (ride the market selectively, never fade it); compare
against a shrunk blend (model proba shrunk toward the vig-free implied
probability) as the staking input. Deliberately scheduled last, after every
feature experiment (#3–6) has settled, so the rule is designed around the
final model's calibration. Evaluated on the same OOF-with-odds fights via
`scripts/odds_backtest.py` on the desktop — model artifacts unchanged, so
no McNemar gate; the gate IS the ROI comparison against the current rule on
identical fights.
Expectation (written before the run): flat/Kelly ROI improves mainly by
*not betting* the worst segment; total bet count drops sharply. If no
positive-ROI rule exists at closing odds, that finding gets recorded
honestly — the model then needs to get better, not the staking cleverer.

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

Market comparison (5786/7869 OOF fights matched to closing odds, 74%
coverage, scripts/odds_backtest.py):
    accuracy:     model 61.2% vs market favourite 66.3%
    prob quality: model log-loss 0.6422 vs market log-loss 0.6089
    dollar value: flat ROI -0.5% (5368 bets, hit 39.0%), kelly ROI +0.9%,
                  close-vs-onesided segment ROI -9.5% (1637 bets, hit 25.5%)

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
Market comparison (5786/7869 OOF fights matched to closing odds, 74%
coverage, scripts/odds_backtest.py):
    accuracy:     model 61.2% vs market favourite 66.3%
    prob quality: model log-loss 0.6431 vs market log-loss 0.6089
    dollar value: flat ROI -0.8% (5378 bets, hit 38.7%), kelly ROI +0.6%,
                  close-vs-onesided segment ROI -9.8% (1728 bets, hit 25.5%)
Baseline v2 leads on every metric here (higher flat ROI, higher kelly ROI,
better segment ROI, better log-loss) — tie-break goes against scorecards.
Decision: REVERTED — pooled-OOF McNemar was a statistical tie (p=0.8312);
the profitability tie-break favors baseline v2 on every metric, and the
$100 Belgrade replay showed no advantage either. Static coverage (mid-2020
→late-2024, frozen) only shrinks going forward; a scorecards-v2 sourced from
ufcstats' own judge totals (~4x coverage, weekly-refreshed) is the queued
successor idea.

### 3. Career-average decay basis — two-round search, status quo kept        2026-08-04, decided WITHOUT a gating retrain
Change investigated (one variable): the `avg_*` EWM decay basis — wall-clock
halflife (round 1, desktop GPU), then fight-count halflives vs a flat career
mean, every candidate pin-eligible (round 2, cloud CPU, committed CSVs).
Round-1 results are recorded in the queue notes above. Round 2 (proxy CV:
`avg_*_diff` block alone, default XGBoost, pinned 72/6 window, pre-holdout):

```
halflife 2 fights : AUC 0.5372
halflife 3 fights : AUC 0.5307
halflife 5 fights : AUC 0.5306   <- production formula
halflife 8 fights : AUC 0.5355
halflife 12 fights: AUC 0.5336
halflife 20 fights: AUC 0.5383   <- nominal top
flat (no decay)   : AUC 0.5333
3.0y wall-clock   : AUC 0.5281   <- round-1 winner, now LAST
```

The ordering is erratic (2 and 20 fights on top, 3/5 at the bottom — no
dose-response curve) and round 1's winner finished last in round 2:
rankings that don't replicate are fold noise, not signal. Autocorrelation
(both units, floor-decay fits): pooled correlations decay extremely slowly
(0.177 → 0.119 over 6 years; 0.176 → 0.110 over 11 fights); fits mostly
degenerate (floor pinned at 0), with `sig_str_frac` the one stat showing an
identified fast form component over a real floor (a=0.105, h=1.23y).
Finding: fighter stat profiles are highly persistent, and short-term form
is already carried by dedicated features (`prev_win`, streaks,
`days_since_last`, Elo) — the career-average decay formula is a non-factor
for this model.
Market comparison / McNemar / $100 replay: N/A — no candidate shipped; the
model and artifacts are unchanged (baseline v2 remains current).
Decision: KEEP the production 5-fight halflife (`AVG_SPEC` pinned
`("fights", 5)`); the wall-clock change was REVERTED before ever training a
gated model. The decay question is CLOSED — don't re-tune it without new
evidence. (Possible far-future lead, not queued: `sig_str_frac`'s fast form
component hints per-family decay could matter for accuracy-type stats
specifically.)
