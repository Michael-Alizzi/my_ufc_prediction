# Methodology

Every modeling concept in the pipeline, explained twice: the math first,
then what it means in plain terms with a worked example. Kept in sync with
the code by rule (CLAUDE.md → Experiment protocol): any change to features,
data, or algorithm updates this file in the same commit.

Pipeline order (notebook `ufc_prediction_claude.ipynb`): load/clean → merge
→ feature engineering → target/feature selection → window search → Optuna
tuning → holdout split → ensemble + calibration → decision layer →
stability/paired checks → export for serving.

---

## 1. The prediction target

**Math.** Each fight is one row with paired red/blue-corner features. The
label is
$$y = \mathbb{1}[\text{red corner wins}]$$
and the model estimates $p = P(y=1 \mid \mathbf{x})$ with gradient-boosted
trees. Draws/no-contests are dropped (no label).

**Plain.** One row per fight, and we predict the probability the red-corner
fighter wins. Nothing fight-internal (strikes landed *in that fight*, etc.)
may appear as a feature — only what was knowable *before* the cage door
closed.

## 2. Corner mirroring

**Math.** For each training row $(\mathbf{x}, y)$ with paired features
(swap map $\sigma$ exchanging `r_*`↔`b_*`, negating `*_diff`), we add
$(\sigma(\mathbf{x}), 1-y)$. The augmented training distribution is
symmetric by construction: $P(y=1)=0.5$ exactly.

**Plain.** Promoters list the favourite as the red corner more often than
not, so a lazy model could score ~58% by always picking red. Duplicating
every fight with the corners swapped and the label flipped removes that
shortcut — the model can only learn from *differences between the fighters*.
Example: Makhachev (red) beats Volkanovski (blue) becomes two rows:
Makhachev-red wins AND Volkanovski-red loses.
Consequence: **every** corner feature must exist as an `r_*`/`b_*` pair (and
`*_diff` must negate under the swap), or the mirror silently corrupts it —
this is enforced by a test.

## 3. Prior-fights-only features (leakage discipline)

**Math.** A feature of fighter $f$ at fight $t$ may use only their fights
$1..t-1$: cumulative-sum aggregates are computed as
$\text{prior}_t = \sum_{i\le t} v_i - v_t$ (the "cumsum-minus-current"
pattern), and rolling means are shifted one fight. Debuts get NaN.

**Plain.** The row for a fight must describe the fighters *as they walked
in*, not as they walked out. If a career KO-rate included the current
fight's KO, the model would be reading the answer key. NaN on debut is
honest ("we know nothing yet") and XGBoost/LightGBM route NaNs natively, so
no imputation is needed. Two implementation traps documented from
experience: pandas `groupby(...).ewm(...).mean().shift(1)` shifts across
fighter boundaries (each fighter's first row would receive the *previous
fighter's* last value) and needs an explicit first-fight NaN mask; the
cumsum pattern is group-safe.

## 4. Career averages (exponentially weighted)

**Math.** For a stat sequence $x_1..x_{t-1}$ over a fighter's prior fights,
the EWM mean with halflife $h$ (in fights) is
$$\bar{x}_t = \frac{\sum_{i<t} w_i x_i}{\sum_{i<t} w_i},\qquad
  w_i = 0.5^{(t-1-i)/h}$$
Current setting: $h = 5$ fights. Medians (`med_*`) are rolling medians of
the same windows; near-duplicate medians (corr > 0.95 with their mean twin
on pre-holdout data) are dropped.

**Plain.** A fighter's last few fights say more about who they are today
than fights from 2015, so recent fights get more weight — with a 5-fight
halflife, a performance five fights ago counts half as much as the latest
one. Example: a fighter whose significant-strike accuracy went
40%, 45%, 50%, 55%, 60% over five fights has an EWM average pulled toward
~55%, not the flat 50%. (Planned experiment: wall-clock halflife — decay by
*years* rather than fight count — which differs mainly for fighters with
long layoffs.)

## 5. Elo rating

**Math.** Ratings start at 1500. After each fight, with
$E_r = \left(1+10^{(R_b-R_r)/400}\right)^{-1}$ (red's expected score),
$$R_r \leftarrow R_r + K\,(S_r - E_r),\qquad K=32$$
and symmetrically for blue. A fight's features use both fighters' ratings
*before* the update (sequential chronological loop — each rating depends on
both fighters' entire prior graphs, so it cannot be vectorised like the
other features).

**Plain.** Elo is a strength score that moves after every fight: beat a
strong opponent and you gain a lot; beat a weak one and you gain little.
Example: a 1500-rated fighter upsetting a 1700-rated one has expected score
$E \approx 0.24$, so they gain $32 \times 0.76 \approx +24$ points and the
favourite loses 24. It summarises strength-of-schedule that raw win/loss
records can't see.

## 6. Judge-scorecard history (decision-quality profile)

**Math.** For a scored decision with per-judge totals
$(r_j, b_j)_{j=1..3}$, define the fighter-perspective margin
$m = \operatorname{median}_j (r_j - b_j)$ (negated for the blue corner)
over $n$ completed rounds. Three career, prior-decision aggregates:
$$\text{avg\_dec\_margin} = \overline{m/n},\quad
  \text{close\_dec\_rate} = \overline{\mathbb{1}[|m|\le 1]},\quad
  \text{dominant\_dec\_rate} = \overline{\mathbb{1}[m > n]}$$
The dominance test is a pigeonhole bound: if every round margin were $\le 1$
(all 10-9), the total margin would be $\le n$; $m > n$ therefore implies at
least one 10-8 (or wider) round. (Point deductions can also produce it —
rare, accepted noise.)

**Plain.** Two fighters can both be "3-0 in their last three" while one won
three 30-27 sweeps and the other survived three split decisions — the win
column can't tell them apart, the scorecards can. The median judge is used
because with three judges the median always sides with the majority and is
immune to one OCR-mangled or rogue card. Margins are per-round so a 50-45
five-rounder (margin 5 over 5 rounds = 1.0/round) correctly outranks a
29-28 (0.33/round). Close-decision rate flags fighters who "live on the
judges' mercy"; dominance rate flags fighters who take rounds 10-8.
Coverage caveat: the UFC only publishes scorecards since mid-2020 and the
vendored file ends late-2024, so these are NaN outside that window — the
models treat NaN as "unknown", exactly right here.

## 7. Walk-forward cross-validation and window search

**Math.** Folds slide over calendar months: fold $k$ trains on
$[T_k - W_{tr},\ T_k)$ and tests on $[T_k,\ T_k + W_{te})$, stepping by
$W_{te}$. Pooled out-of-fold (OOF) predictions across folds are scored by
AUC. The window pair $(W_{tr}, W_{te})$ is chosen by grid search over the
same scheme, **restricted to data before `HOLDOUT_START`** (the final 6
months are excluded from every selection decision). One honest caveat: the
grid's combinations pool over slightly different evaluation periods (a
6-month-train combo can be scored on early-90s folds a 72-month combo never
reaches), so the comparison is not perfectly apples-to-apples; restricting
scoring to a common period is a known possible refinement.

**Plain.** Never shuffle fight data: a random split would train on 2024
fights and "predict" 2019 ones, letting the model exploit era knowledge
(rule changes, judging trends, evolving meta) that doesn't exist at
prediction time. Walk-forward CV always trains on the past and tests on the
following months, exactly like deployment. The window search answers "how
much history helps?" — too little is noisy, too much drags in a stale meta.
The window is **pinned** between deliberate re-searches so experiments
change one thing at a time.

## 8. Hyperparameter search (Optuna / TPE)

**Math.** The Tree-structured Parzen Estimator models
$P(\text{params} \mid \text{score good})$ and
$P(\text{params} \mid \text{score bad})$ from completed trials and proposes
parameters maximising their ratio. Objective: pooled walk-forward AUC on
pre-holdout data. 100 trials, shared across machines via a
PostgreSQL-backed study (both workers see every completed trial live).

**Plain.** Instead of trying random parameter combos, TPE learns which
regions of parameter space produce good scores and samples there more
often — like a chef tasting as they season instead of following a fixed
grid of recipes. The desktop and laptop each run trials against the same
scoreboard, so the search is one coordinated 100-trial effort, not two
blind 50s.

## 9. The ensemble

**Math.** Final score
$$p = (1-w)\cdot\tfrac{1}{3}\textstyle\sum_{k=1}^{3} p_{\text{xgb}_k} + w\cdot p_{\text{lgbm}}$$
with the top-3 Optuna XGBoost trials refit on the final training window and
$w \in \{0, 0.25, 0.5\}$ chosen by validation AUC.

**Plain.** Averaging three good-but-different XGBoost configurations cancels
some of each one's individual quirks; LightGBM (a different algorithm
family) is blended in only if the validation slice says it helps. Only
three candidate weights are considered on ~120 validation fights — a finer
grid would overfit the slice (see §11 for the same logic).

## 10. Probability calibration (Platt, centered)

**Math.** A logistic regression with no intercept fit on centered pooled-OOF
scores: $\hat{p}_{\text{cal}} = \sigma(\beta (p_{\text{raw}} - 0.5))$, so
$p_{\text{raw}} = 0.5 \Rightarrow \hat{p}_{\text{cal}} = 0.5$ exactly.
Gated by a Brier-score non-regression assertion on the OOF pool.

**Plain.** Boosted trees rank fights well but their raw scores aren't
frequencies ("0.7" might win 65% or 80% of the time). Calibration reshapes
the displayed confidence so that fights shown as 70% really win about 70%
of the time — fit on thousands of pooled walk-forward predictions, never on
the tiny validation slice. Pinning 0.5→0.5 guarantees the displayed
favourite always matches the decision (§11). Example: raw 0.62 might
display as 0.68 after calibration; raw 0.50 always displays as 0.50.

## 11. The fixed 0.5 decision threshold

**Math.** Winner $= \mathbb{1}[p \ge 0.5]$. Not tuned. Mirroring (§2) makes
the training prior exactly 0.5, so 0.5 is the natural operating point.

**Plain.** An earlier version tuned the threshold on ~120 validation fights
and lost 6 points of test accuracy — a textbook case of fitting noise in a
small sample (±9-point CI, §12). The threshold stays at the symmetric
default; probability quality is handled by calibration, not by moving the
cutoff.

## 12. Evaluating a run

**Math.** Test accuracy $\hat{p}$ over $n \approx 110$ fights carries a CLT
interval $\hat{p} \pm 1.96\sqrt{\hat{p}(1-\hat{p})/n} \approx \pm 9$ points.
Paired model comparison uses McNemar's test on the discordant fights
($b$ = baseline-right/new-wrong, $c$ = baseline-wrong/new-right):
exact binomial $c \sim \text{Bin}(b+c, 0.5)$ on the test set;
$\chi^2 = (|b-c|-1)^2/(b+c)$ on the pooled-OOF comparison. The **primary
gate** is McNemar on ~6k aligned pooled-OOF fights (both models' OOF over
the identical fold scheme; the baseline's is stored in its artifact); the
110-fight test set is a sanity check only.

**Plain.** With 110 test fights, a "2-point improvement" is indistinguishable
from luck — the error bar is ±9. Comparing two models on the *same* fights
helps a lot (McNemar looks only at fights where they disagree), but even
then ~20 disagreements can't certify small gains. That's why experiments
are judged on ~6,000 pooled walk-forward predictions: a real 1-point edge
is visible there, and invisible on 110. Example: baseline right / new wrong
on 8 fights, reverse on 19 → McNemar $p \approx 0.05$; on the test set the
same ratio would be 1-2 fights and meaningless.

## 13. Betting layer (Kelly staking)

**Math.** For decimal odds $o$ and model probability $p$, edge $= po - 1$;
the Kelly fraction is
$$k = \frac{po - 1}{o - 1}\ \text{if } po > 1,\ \text{else } 0.$$
The weekly job splits a fixed $100 bankroll across all value sides
proportionally to $k$ (stakes sum to $100 — total risk, not per-bet risk).

**Plain.** Bet only when the model thinks a side is likelier than the price
implies, and bet more the bigger the edge. Example: model says 55% at odds
2.10 → edge $= 0.55 \times 2.10 - 1 = 0.155$, Kelly
$= 0.155/1.10 \approx 14\%$ of bankroll. The value side can be the fighter
the model expects to LOSE — a near-coin-flip priced as a lock is value on
the underdog. Model edge over bookmakers is unproven; the $100 framing caps
worst-case loss by design.

## 14. Serving-time reconstruction

**Math.** Serving builds a feature row from each fighter's most recent
history row, reoriented so the `r_*` side always describes that fighter;
blue-corner features are read from the blue fighter's *reoriented red side*
(`own_value`), and every `*_diff` is computed from an exported exact source
map (`diff_pairs`, verified $d = r - b$ column-wise at export).

**Plain.** A fighter's last row might have them in the blue corner, and
even after reorienting, the row's *other* side describes their last
opponent. Reading the wrong side served ~half the feature vector from the
wrong fighter for months (EXPERIMENTS.md entry 0) — predictions for
Makhachev–Holloway quietly used McGregor's height and layoff. The rule now:
one serving implementation (`predict.build_features`), used by the app, the
weekly job, and the notebook alike, tested by comparing served values
against each fighter's own history for a pair who never met (a pair who
last fought *each other* hides this bug class — their "last opponent" is
each other).

## 15. Experiment protocol and the $100 replay

See CLAUDE.md (protocol) and EXPERIMENTS.md (log + template). One variable
per retrain; pooled-OOF McNemar decides; rejected changes are fully
reverted. The $100 replay always scores the **logged pre-event
predictions** from `weekly-predictions-log` — re-predicting a past event
through current history is forbidden because the event's outcome is already
inside `head_to_head` and both fighters' last rows (self-inclusion leak).

## 16. Security notes

- `ensemble.joblib` / `fighter_history.parquet` are pickle-family artifacts:
  loading them executes code by design. Only ever load the repo's own
  committed artifacts — never a downloaded or user-supplied file.
- Optuna's shared-study credentials live only in the environment
  (`OPTUNA_STORAGE_URL`, `OPTUNA_WORKER_STORAGE_URL`); a DB password was
  once committed here and a Gmail app password once leaked into git history
  (revoked) — secrets never go in the repo, including in notebook cells.
- The weekly card JSON is operator-supplied and schema-light by choice; it
  is never fetched from an untrusted source.
