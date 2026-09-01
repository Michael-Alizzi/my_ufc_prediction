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
