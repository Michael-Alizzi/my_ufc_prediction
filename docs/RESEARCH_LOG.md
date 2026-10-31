# Research Log

Dated entries from the `ufc-monthly-research` Routine (1st of each month):
what was surveyed, sources, and a verdict per idea. Ground rules: at most
ONE retrain-worthy change per month, judged against the market-facing
metrics (log-loss gap to the vig-free market, ROI at closing odds); ideas
already tried and rejected in EXPERIMENTS.md need NEW evidence to be
re-raised; "no change warranted" is the expected outcome most months.

Verdicts: **adopt-candidate** (proposed to Michael now), **queue**
(worth doing, not this month / not yet), **rejected** (with reason).

---

## 2026-09-01 — first run

**Surveyed** (WebSearch sweep, ~last 3 months of literature + news):

*Tabular ML*: TabArena leaderboard state ([The state of Tabular Foundation
Models, 2026](https://mindfulmodeler.substack.com/p/the-state-of-tabular-foundation-models));
[TabPFN-2.5](https://arxiv.org/pdf/2511.08667); [TabICLv2](https://arxiv.org/pdf/2602.11139);
[Pocket Foundation Models: distilling TFMs into CPU-ready gradient-boosted
trees](https://arxiv.org/pdf/2605.18654).
*Betting/markets*: [Miller & Nichols 2026, favorite-longshot bias in MMA
betting markets](https://link.springer.com/article/10.1007/s12197-026-09757-x)
(J. Econ. & Finance); [Fight Matrix on closing line value in
MMA](https://www.fightmatrix.com/2026/08/23/closing-line-value-in-mma-was-it-a-good-price/);
[calibration-vs-accuracy for betting model selection](https://www.sciencedirect.com/science/article/pii/S266682702400015X);
[odds-only vs GLM forecasting under EMH](https://arxiv.org/pdf/2604.17194).
*UFC news*: the Nov-2024 unified-rules amendment (12-6 elbows legal,
grounded-fighter definition) plus the ABC 2025 damage-first judging
clarification; Paramount+ move reshaping matchmaking; no new weight
classes.

**Verdicts:**

1. **CLV (closing-line value) logging — ADOPTED (Michael approved
   2026-09-01; PR opened the same day).** We bet at
   Friday-morning prices; recording each bet's closing odds at scoring
   time would measure whether our prices beat the close — the standard
   early indicator of real edge, converging far faster than win/loss
   (it grades the price, not the coin flip). Small change to the Monday
   scoring job + one ledger/`collected_odds` column; touches betting
   code so it ships as a PR for Michael to merge, and changes
   measurement only — no model, no staking, no trial interference.
2. **TFM→GBT distillation ("Pocket Foundation Models") — queue.**
   Directly attacks the exact reason TabPFN was rejected twice (entries
   8b/8g: GPU-only or CPU-infeasible serving) by distilling the TFM into
   CPU-servable boosted trees. Genuinely NEW evidence, so the retread
   bar is met — but the method is a fresh 2026 paper with no hardened
   tooling yet; revisit when reference code matures. This is the
   strongest future retrain candidate on the board.
3. **4th `rules_era` level for the Nov-2024 rule amendment — queue.**
   A real data-generating-process change (12-6 elbows, grounded
   definition, damage-first judging emphasis), cleanly implementable as
   one ordinal level. Mechanism for beating the market is weak though —
   the market knows the rules changed too — so it waits behind
   higher-impact work.
4. **Favorite-longshot bias exploitation (Miller & Nichols) — queue,
   post-trial.** Could inform a staking filter, but staking rules are
   frozen mid-trial by entry 9's pre-registration; revisit when the
   10-event trial resolves, alongside the C/E/F verdict.
5. **TabPFN-2.5 / TabICLv2 as ensemble members — rejected (retread).**
   Serving constraint unchanged from 8f/8g: cloud-CPU weekly job can't
   run TFM inference; the distillation route (#2) is the live version of
   this idea.
6. **Calibration-first model selection — rejected (already
   implemented).** The OOF logistic stacker optimizes log-loss (entry
   8d) and the market comparison already gates on log-loss vs the
   vig-free market; the literature confirms the design rather than
   changing it.

**Judgement call: NO retrain this month.** Nothing surveyed beats the
one-variable bar for a market-gap improvement right now. The CLV logging
diagnostic (#1) was proposed, approved by Michael the same day, and
shipped as a PR.

---

## 2026-10-01 — second run

**Surveyed** (WebSearch sweep, roughly Jul–Sep 2026, plus one in-repo
measurement that the literature pointed at):

*Tabular ML*: [TabPFN-3.5 technical report](https://arxiv.org/abs/2609.17895)
and [changelog](https://docs.priorlabs.ai/changelog/tabpfn-3.5) (Sep 2026;
3.5-Fast up to 3–6× faster inference; `tabpfn` 9.0.0);
[TabPFN v8.2.0](https://newreleases.io/project/github/PriorLabs/TabPFN/release/v8.2.0)
(bf16 autocast on AMX/AVX512-BF16 CPUs, ~2× CPU inference; this cloud box
has both flags); [Prior Labs model licences](https://docs.priorlabs.ai/models)
(every weight set incl. v2 is non-commercial); [TabFM zero-shot TFM](https://arxiv.org/pdf/2609.37959)
(29 Sep, tops TabArena); [Mitra-v2](https://arxiv.org/pdf/2609.04540);
[Pocket Foundation Models](https://arxiv.org/abs/2605.18654) — code now
shipped as `TabDistiller` in [TabTune](https://github.com/Lexsi-Labs/TabTune)
(MIT; teacher TabICLv2, students LightGBM/XGBoost/CatBoost; +0.011 AUC over
tuned CatBoost on <21-feature data but only +0.001 on >21 features);
[Ensembling TFMs: a diversity ceiling and a calibration trap](https://arxiv.org/abs/2605.18696)
(logistic-regression stackers win accuracy but rank worst on log-loss);
[Classifier calibration at scale](https://arxiv.org/html/2601.19944v1)
(Platt and isotonic *systematically degrade* proper scores for strong
GBDTs; Beta/Venn-Abers as starting points, "not guaranteed to improve");
[XGBoost 3.1](https://xgboost.readthedocs.io/en/latest/changes/v3.1.0.html)
/ LightGBM 4.7 — incremental, nothing modelling-relevant.
*Betting/markets*: [Miller & Nichols 2026](https://econpapers.repec.org/article/sprjecfin/v_3a50_3ay_3a2026_3ai_3a1_3ad_3a10.1007_5fs12197-026-09757-x.htm)
re-read (correction to last month, below); [in-play football forecasting
calibrated to Betfair](https://arxiv.org/html/2605.16066) (May 2026:
"comparable forecast quality does not translate into comparable economic
value"; market information dominates accuracy); [Conformal Kelly](https://arxiv.org/abs/2608.01494)
(Aug 2026; dev-window 28.5%/yr collapsed to 7–8.5% out of sample);
[Risk parity vs Kelly in football value betting](https://link.springer.com/chapter/10.1007/978-3-032-27272-0_19)
(15% fractional Kelly best of the tested fractions over 17k matches);
CLV explainers ([Fight Matrix](https://www.fightmatrix.com/2026/08/23/closing-line-value-in-mma-was-it-a-good-price/),
trade press) — nothing beyond what entry PR #27 already logs.
*UFC news*: ABC conference 3–5 Aug 2026 (Orlando) had two Unified-Rules
items on the agenda — referee discretion on intentional/accidental fouls,
and the vomiting/loss-of-bodily-function TKO wording
([Bloody Elbow preview](https://bloodyelbow.com/2026/04/17/ufc-could-undergo-two-rule-changes-seemingly-as-a-result-of-recent-controversies-inside-the-octagon/));
no report of the vote found, and both affect only DQ/NC edge cases. No
new weight class. Roster: nine cuts mid-September plus the Contender
Series intake ([MMA Mania tracker](https://www.mmamania.com/ufc-roster-watch-cuts-tracker-free-agent-aquisitions-mma)) —
seasonal, debutants are unpredictable by the model anyway. Finish rates:
[mma.social](https://mma.social/stats/finish-rates) has 2026 YTD at 56.2%
finishes / 38.2% KO (highest in its 2021+ table; 2024 was 44.8%), while
[Fight Matrix](https://www.fightmatrix.com/2026/07/31/how-fights-actually-end-finish-rates-by-weight-class/)
reads 2015–2025 as 44.5–52.6% "without direction". Noted, not actionable:
the model predicts the winner, not the method, and the market sees the same
cards.
*Data sources*: [UFCalendar fight API](https://www.ufcalendar.com/blog/ufc-api-python-fight-data-tutorial)
(round-by-round stats split by target/position), tidytuesday `fightr`
(2026-07-07), refreshed Kaggle/HF ufcstats dumps — all ufcstats-derived;
the only genuinely new *shape* is per-round splits (see verdict 7).

**In-repo measurement (prompted by the calibration paper + KAN-57).**
The shipped artifact's pooled OOF (7,869 fights, raw stacked score):

- Scored on a **mirrored pool** (both orientations of every fight, so the
  red-corner base rate cancels — the KAN-57 shift-vs-symmetric split): raw
  log-loss 0.6009 / Brier 0.2083; the live calibrator σ(4.615·(p−0.5))
  gives 0.6029 / 0.2087. Refitting the same prob-space slope on the
  mirrored pool lands at β=4.66 and the same numbers; a *logit*-space
  slope refits to exactly 1.000 (identity). Reliability by band on the
  mirrored pool is within 1.5 points everywhere (0.132→0.124, 0.250→0.265,
  0.354→0.360, 0.456→0.442, 0.544→0.558, 0.646→0.640, 0.750→0.735,
  0.868→0.876). Same picture on 2010+ only. Conclusion: the raw stacked
  score is already calibrated; the symmetric component the calibrator
  exists to fix is nil, and its functional form (sigmoid of a *linear*
  function of p) cannot express the identity, so it can only distort.
- Chronological 5-block cross-fit on the un-mirrored pool: live form
  0.6030, logit-Platt 0.6010, raw 0.6009; isotonic 0.6050 — matching the
  paper's finding that post-hoc calibration degrades strong GBDT scores.
- Stake impact (the FAQ's "26% bigger stake" point, now across the range):
  at p=0.60/odds 1.80 Kelly 0.100→0.130; 0.70/1.55 0.155→0.199;
  0.45/2.40 0.057→0.044; 0.35/3.20 0.055→0.031. Live stakes over-bet
  mid-favourites ~30% and under-bet underdogs 20–45% relative to the raw
  probability that every backtest (entries 5–10, rule selection, rule F's
  λ, the History replay) actually scored.
- **Corner-orientation artifact in the raw data**: ufcstats lists the
  *winner* in the red corner for 95–100% of fights every year 1994–2009
  (e.g. 2008: 201/201), dropping to the normal 54–62% favourite-as-red
  rate from 2010. The FAQ's "red wins 63% because the favourite is listed
  red" is the blend of those two regimes; in the clean 2010+ era the
  base-rate shift is +3.8 points (logit intercept 0.15), not 7.6. Harmless
  to the model (mirroring makes it orientation-blind; features are paired)
  and to the market comparison (orientation-free metrics), but any
  diagnostic that reads the corner label — the KAN-57 shift table, an
  intercept "edge" — must exclude pre-2010 rows. Recorded in
  docs/DATA_DICTIONARY.md.

**Correction to the 2026-09-01 entry.** Verdict 4 described Miller &
Nichols as finding a favourite-longshot bias in MMA. The paper finds **no**
such bias (MMA "largely efficient"; the residual inefficiencies it names
are youth and travel advantages and favourites in women's bouts, with
"few statistically significant positive returns" out of sample). Age and
home-crowd are already features here, so the paper confirms the design
rather than opening a staking angle; that queued item is withdrawn.

**Verdicts:**

1. **Drop the probability calibrator; stake and display off the raw
   stacked score — ADOPT-CANDIDATE (the one change; no retrain).** This is
   KAN-57's "decide from the evidence whether the calibrator stays, and
   make the backtest and the weekly job agree" with the evidence now in
   hand: the raw score is calibrated on the orientation-free pool, the
   calibrator is strictly net-negative (+0.002 log-loss, the size of the
   8d/8e gains that were *accepted* on log-loss), and it is the only
   reason live stakes differ from every backtested number. Mechanism for
   the market metrics is direct — the trial's rules were validated on raw
   probabilities and are being staked on a worse one. Implementation:
   `predict_winner` returns the stacked probability; the notebook's
   Probability Calibration cell and the artifact's `calibrator` key go
   (fail loudly on an old artifact rather than silently fall back); the
   0.5 decision rule and antisymmetry are untouched because the stacker
   has no intercept. Serving/betting code, so a PR for Michael. **Timing
   is Michael's call**: the 10-event trial (7 scored, cards 3/10/17 Oct,
   graded ~19 Oct) froze the staking inputs, so the clean path is to merge
   after the tenth event is graded; shipping earlier treats it as a bug
   fix and the entry must say the last ≤3 trial cards staked on raw.
   Pre-registered in EXPERIMENTS.md → Queued.
2. **TFM→GBT distillation (Pocket FM / TabTune `TabDistiller`) — queue,
   demoted.** The "wait for code" condition from last month is met (MIT
   library, TabICLv2 teacher is openly licensed). But the paper's own
   breakdown says the gain concentrates on <21-feature data (+0.011 AUC)
   and is +0.001 above 21 features; this pipeline has 267. A student is
   also bounded by its teacher, and the strongest TFM evidence here (8f,
   full TabPFN) was worth 0.0007 log-loss. Expected effect sits inside
   refit noise; it stays queued only as the cheapest way to ever get TFM
   signal onto the CPU weekly job.
3. **TabPFN-3.5 / 3.5-Fast / bf16 CPU inference — rejected (retread,
   plus licence).** New speed (3–6× model-side, ~2× bf16 on this CPU) is
   real evidence against 8g's cost finding, but 8g's *value* finding
   stands (CPU-feasible configs added ≤0.001 OOF and lost on the market
   numbers), and every TabPFN weight set — v2 included — is licensed
   non-commercial with "no production use". Note for the record that the
   8f/8g members ran under that licence; moot since both were reverted.
   TabFM, Mitra-v2 and TabICLv2 as direct members: same serving retread.
4. **Non-linear / Beta / Venn-Abers calibration — rejected.** The
   mirrored-pool reliability curve shows nothing for them to fix, and
   cross-fit isotonic is worse than raw by 0.004. Verdict 1 removes the
   calibration layer rather than replacing it.
5. **Stacker calibration-trap paper — no change.** It warns that rich
   logistic stackers sharpen at log-loss's expense; our 8d guardrail
   (member-count coefficients, no intercept, 7.9k rows) is the mitigation,
   and the mirrored-pool slope of exactly 1.000 shows the stacked score is
   not over-sharpened. Keep the guardrail written into any future stacker
   change.
6. **Staking: fractional Kelly / Conformal Kelly / FLB exploitation —
   queue, post-trial (fractional Kelly) / rejected (the other two).**
   Fractional Kelly is the principled successor to the arbitrary 0.25 cap
   and overlaps rule E's mechanism; evaluate on pooled OOF after the trial
   under the entry-9 pre-registration pattern. Conformal Kelly's edge did
   not survive its own out-of-sample window; the FLB idea was a misreading
   (correction above).
7. **Per-round stat trajectories (cardio/fade features from round-by-round
   splits) — queue.** The one new data *shape* found; ufcstats has the
   per-round tables, so it is a scraper change in `../UFC-Predictions`
   plus the usual `r_/b_/diff` plumbing. Mechanism vs the market is
   plausible (late-round output decay is not in the public box score the
   market anchors on) but unevidenced; behind verdicts 1–2.
8. **4th `rules_era` level (Nov-2024 amendment) — stays queued, no new
   evidence.** The two finish-rate sources disagree on whether 2026 is a
   regime shift; the ABC's 2026 agenda items touch DQ/NC only.

**Judgement call: ONE change proposed, NO retrain.** Remove the
probability calibrator so live stakes use the raw stacked probability the
backtests validated (verdict 1) — a serving-code PR, timed around the
trial freeze at Michael's discretion. Nothing surveyed justifies touching
the model or features this month; the TabPFN-3.5 speedups are the most
interesting external development and are still blocked by licence and by
8g's value finding.

---

## 2026-11-01 — third run

**Surveyed** (WebSearch sweep, roughly Aug–Oct 2026, plus the repo's own
October record):

*Tabular ML*: no October release of note. Revisions only — [ScoringBench](https://arxiv.org/abs/2603.29928)
(v4, 12 Oct; proper-scoring-rule benchmark, regression-only),
[TabFORGE](https://arxiv.org/abs/2605.09424) (generative TFM, NeurIPS 2026),
[High performance, low reliability: uncertainty benchmarking for TFMs](https://arxiv.org/pdf/2605.28554),
[one-bit calibration estimation](https://arxiv.org/html/2609.05125) (Sep;
threshold-feedback setting, not ours). Leaderboard noise: [Mitra-v2](https://arxiv.org/html/2609.04540v1),
[TabPFN-3.5](https://arxiv.org/pdf/2609.17895) and [TabFM](https://arxiv.org/pdf/2609.37959)
each claim the top of TabArena on their own reference pools; none is on the
official board yet, and every one is a non-commercial-licensed TFM — the
serving retread closed in 8f/8g and re-confirmed last month. No new
gradient-boosting, stacking or calibration method with credible tabular
evidence appeared in the window.
*Betting/markets*: [The profit-bias identity in sports betting](https://arxiv.org/abs/2609.06739)
(Dmochowski, Sep 2026): bookmaker margin = hold + shading×public-lean +
cov(bet share, outcome); a public lean earns the book nothing without
price shading, and in 1,139 MLB games the realised margin was
indistinguishable from the hold (no shading found). Conceptually useful —
it says a visible public bias is not an exploitable edge unless prices are
shaded — and consistent with Miller & Nichols finding MMA "largely
efficient". No new MMA-specific market paper; nothing new on Kelly/staking
beyond the Baker–McHale shrinkage line we already cover with rules E/F.
*UFC news (data-generating process)*: (1) The ABC's
[Unified Rules 8.2026](https://www.abcboxing.com/wp-content/uploads/2026/08/Unified-Rules-of-MMA-8.2026.pdf)
(amended 5 Aug 2026, **requested implementation November 2027**) are the
two agenda items from last month, now adopted: loss of bodily function in
a round = TKO (medical stoppage), with a bucket/physician procedure when a
foul causes it; accidental-foul stoppages after 2 of 3 / 3 of 5 rounds go
to a Technical Decision on the cards. Edge-case outcomes only, a year
away, state-by-state. (2) CSAC's UFC 331 debrief
([fighthub](https://fighthub-app.com/en/ufc-331-scorecards-csac-debrief-rule-changes/)):
Foster called a 50-45 card "not possible"; discussion items were a lateral
knee-kick foul, a cut-closing peptide, and reclassifying fouls as
incidental/reckless/malicious — none adopted. (3) Ki MMA formally asked
CSAC (1 Dec stakeholders meeting) to legalise knees to a grounded
opponent's head ([Bloody Elbow](https://bloodyelbow.com/2026/10/21/mmas-unified-rules-could-be-changed-with-formal-request-made-over-currently-banned-strikes/));
UFC/ABC position unknown — watch item. (4) Finish rate: 2026 YTD 56.9% on
425 fights ([mma.social](https://mma.social/stats/finish-rates)); UFC 332
set a modern record with 11 KOs / 9 first-round KOs; UFC Vegas 122 had 9
finishes in 12. (5) Roster: a 16-0 bantamweight (Basharat) released 14 Oct
plus the usual Contender Series purge — Bloody Elbow's read is that the
promotion is shedding decision-winners; commentary, not policy. (6) No new
weight class (165 lb remains a perennial rumour, denied). (7) Paramount+
takes Canadian numbered cards from 2027; 2027 schedule starts Dallas 16 Jan.
*Data sources*: same ufcstats-derived mirrors as last month (Kaggle refresh
to Sep 2026 with round splits; UFCalendar per-round API; a paid
"UFC Intelligence API"). Nothing new in shape beyond queue item R4.

**Repo record since 1 Oct (what actually changed the picture):**

- **Entry 9's trial closed at 10 cards with A retained** (E +$99.47 vs A,
  p=0.22; C +$43.07, p=0.27; F −$7.29, p=0.78). Michael replaced the
  re-tested-weekly promotion test with **entry 11's rolling 10-card blocks**
  (one exact sign-flip test per block, Bonferroni over three challengers,
  switch only at block boundaries). Experiment 2 began at UFC 333 with A
  staked; card 2 (Moicano vs Nolan, 31 Oct) is logged, not yet scored.
- **Rule A's run**: −$5.35 net over 11 cards (C +$30.15, E +$84.62,
  F −$13.25), including four straight losing cards in October (−17.5,
  −12.6, −45.1, −23.1). **Avg CLV for A on the 8 cards with snapshots:
  +1.3, +1.4, +1.4, +0.7, +0.8, +0.3, −0.6, +1.1 → mean +0.8%**, positive on
  7 of 8. That is the most interesting number this month: the prices we
  take are, on average, slightly better than the close, while results run
  behind. Too few bets (~35) to call it edge, but it is the direction CLV
  logging was added to detect, and it argues for patience rather than
  rule-tinkering.
- **The October adopt-candidate (drop the calibrator) has not been acted
  on** — `predict.py` still applies σ(4.615·(p−0.5)) to the staked
  probability. Its queue entry was logged as "11" and collided with entry
  11 (the block test); renumbered R1–R4 today. Timing note updated: the
  "after the trial" window no longer exists under rolling blocks, so the
  clean options are the block-2 boundary (~late Dec) or merging now as a
  bug fix with the affected cards recorded.

**Verdicts:**

1. **Drop the probability calibrator (R1) — still the ADOPT-CANDIDATE,
   unchanged, awaiting Michael's go.** Nothing in this sweep weakens the
   October evidence (raw stacked score calibrated on the mirrored pool;
   calibrator net-negative; it alone makes live stakes differ from every
   backtest). Not re-proposed as new work — it is the same single change,
   carried over. Recommended timing: block-2 boundary (after card 20 is
   scored) unless Michael prefers the bug-fix route now.
2. **TFM members / new TFM releases (Mitra-v2, TabPFN-3.5, TabFM, EXAONE
   Tabular) — rejected (retread).** Licence and CPU-serving constraints
   unchanged; no new evidence on the value side.
3. **Profit-bias identity — no change.** Confirms the design stance (no
   favourite-longshot or public-lean exploitation without shading evidence);
   worth citing in the FAQ if the FLB question returns.
4. **ABC 8.2026 amendments / CSAC proposals / Ki MMA request — no change;
   watch items.** Adopted changes are DQ/NC/TKO edge cases with a Nov-2027
   implementation date; the grounded-knee request is the only item that
   would materially change the DGP and it is a California discussion item
   on 1 Dec. The 4th `rules_era` level stays queued without new evidence.
5. **Finish-rate / roster-turnover drift — no change.** The 2026 finish
   rate (56.9%) and the Contender-Series intake are visible to the market
   and to the finish-rate and win-time features; no mechanism vs the
   market.
6. **Fractional Kelly (R3) — queue, now eligible at the block-2 boundary**
   (a staking change under entry 11 belongs at a boundary, same slot as R1).
7. **Per-round trajectories (R4), distillation (R2) — queue, unchanged.**

**Judgement call: NO retrain, NO new change this month.** The only
qualifying change on the board is October's R1, which is still waiting on
Michael; this run adds nothing to it and manufactures nothing beside it.
Most interesting finding: rule A is beating the close (+0.8% average CLV,
7 of 8 cards) while running −$5 over 11 cards — exactly the pattern CLV
logging exists to separate from bad luck.
