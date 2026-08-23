# FAQ

Questions that have actually come up while running this project, with the answers
worked out at the time. **Standing rule: every new question asked in-session gets
appended here** (and the dashboard's FAQ tab republished with it). Deeper treatments: [METHODOLOGY.md](METHODOLOGY.md) (the
maths behind every feature and the validation scheme), [DATA_DICTIONARY.md](DATA_DICTIONARY.md)
(every column), and [../EXPERIMENTS.md](../EXPERIMENTS.md) (the run-by-run record —
entry numbers cited below refer to it).

---

## Betting

### How is my money actually staked each week?

By **rule A**, the production staking rule (chosen in entry 9). For each fight the
model outputs a win probability `p`; the bookmaker's decimal odds imply one. A side
qualifies as a *value bet* when

```
p × odds − 1 > 0
```

i.e. the expected return per $1 staked exceeds the dollar in. At most one side per
fight can qualify. The week's bankroll (`--bankroll`, e.g. $50) is then split across
all qualifying sides **proportionally to each side's Kelly fraction** (capped at
0.25), rounded to whole dollars, with any rounding leftover going to the largest
bet. The code path is `predict.py:kelly_edge` + the stake-splitting block in
`send_weekly_predictions.py`; the bankroll is the declared maximum loss for the card.

### What does the Kelly fraction represent?

The answer to: *"if my probability estimate is right, what fraction of my bankroll
should this bet get to maximise long-run compound growth?"* Bet less and you waste
edge; bet more and losing streaks compound against you (lose 50% and you need +100%
to recover) — Kelly (1956) proved a unique optimum in between:

```
f = (p × odds − 1) / (odds − 1)
```

The numerator is the edge (no edge → no bet). The denominator — profit per dollar
if the bet wins — accounts for payoff asymmetry: short-priced favourites need more
stake per unit of edge (small payoff), longshots less. Calibration point: a 55%
coin flip at even money gives f = 0.10 — even a solid edge only ever justifies a
modest slice of bankroll.

Two caveats. Kelly is only optimal if `p` is *correct*; an overconfident model
systematically overbets (this is the failure mode rule E targets). And the weekly
job uses the fractions as **relative weights** to split a fixed bankroll, not as
literal fractions of total wealth — more conservative than true Kelly, but it keeps
the core insight: stake proportional to edge, discounted by payoff asymmetry.

### Why is the Kelly fraction capped at 25%?

Because full Kelly is only optimal if the model's probability is exactly
right, and Kelly bets biggest precisely where the model disagrees with the
market most — which, given the market's better calibration overall, is
where the model is most likely wrong. Overbetting is an asymmetric sin:
past the true Kelly fraction growth degrades, and past ~2× it turns
negative — you can lose money on a genuinely profitable edge by staking
too much. The cap truncates exactly those least-trustworthy bets (normal
bets size at 1–15% and never feel it), bounds the single-fight worst case
at a quarter of the bankroll, and was fixed a priori rather than tuned
(entry 9's pre-registration bans fitted thresholds). Practitioners' usual
half-/quarter-Kelly discount is the same humility idea; rule E's
shrink-toward-market is its more principled cousin.

### Instead of a fixed 25% cap, can we measure how correct the model's probability is and use that?

Yes — the measurement exists and was run (Aug 2026). Blend model and
market in log-odds space, `logit(p') = λ·logit(model) + (1−λ)·logit(market)`,
and fit λ by maximum likelihood on the first half of history: **λ ≈ 0.78**
— the model's estimate earns ~78% of the say (high partly because the
odds-aware model already contains the market as a feature). But scored on
the held-out second half, the fitted blend (kelly ROI +5.0%) beat raw rule
A (+4.1%) yet clearly lost to rule E's crude fixed 50/50 shrink (+9.2%).
The reason: the model's edge decays over time, so a trust weight fitted on
the strong years is overconfident in the weak ones — a fitted parameter
chases the past, a humble fixed shrink is robust to the drift (the same
winner's-curse logic behind entry 9's no-tuned-thresholds rule). Side
findings: with any shrinkage the 25% cap becomes nearly redundant
(uncapped +5.5% ≈ capped), and the odds-aware model narrowly beats the
market's own log-loss on recent data (0.6073 vs 0.6081). Net: the idea is
right, and rule E — currently in the live 10-event trial — is its robust
implementation. The fitted version now also runs live as **shadow rule F**
(entry 10): λ frozen at 0.746 (full-pool fit, never refit mid-trial), so
the forward ledger adjudicates E-vs-F directly; pre-registered expectation
is that E outperforms it.

### Worked example — UFC 330 (Aug 2026, $50 bankroll)

Step 1, the value test (`p × odds`), model probability vs Sportsbet price:

| Side | p | odds | p×odds | value? |
|---|---|---|---|---|
| Makhachev | .789 | 1.286 | 1.015 | yes, barely |
| Alvarez | .757 | 1.385 | 1.048 | yes |
| Donte Johnson | .763 | 1.40 | 1.068 | yes |
| Magny | .544 | 1.91 | 1.039 | yes |
| Ribovics | .835 | 1.182 | 0.987 | no — 1.3¢ short |
| Turner | .637 | 1.556 | 0.991 | no — 0.9¢ short |

(Ribovics and Turner: high-confidence picks whose price already charges full
freight — a confident pick and a good bet are different things.)

Step 2, Kelly fractions: Johnson (.068 edge ÷ .40 payoff) = **.171**; Alvarez
= **.126**; Makhachev = **.051**; Magny (.039 ÷ .91) = **.043**. Sum ≈ .391.

Step 3, stakes = 50 × f/.391 → **$22 Johnson, $16 Alvarez, $6 Makhachev, $6 Magny**
(full-precision probabilities; recomputing from the rounded table lands within $1).

### Why does the model sometimes bet on the fighter it predicts to LOSE?

Because value lives in the gap between model and market, not in who's more likely
to win. If the model has a fight at 54/46 but the market prices the favourite like
a 70/30 lock, the *underdog's* price overpays their true chance — that side is the
value bet even though the model expects them to lose. The bet column answers "where
is the price wrong?", not "who wins?".

### Why do most fights get $0?

Bookmaker prices are good — the 2026 backtest (entries 1–2) showed closing
favourites win 66.3% of fights with better probability calibration than the model.
Most of the time the price already reflects everything the model knows, so
`p × odds` lands below 1 on both sides and betting either would be −EV. A typical
card has 8–9 no-bets out of 12; the discipline of passing is where the rule's ROI
comes from.

### In the History bet table, why does a win show less than $1? Is P/L the amount won excluding my stake?

Yes — P/L is **profit on a $1 stake, with the stake netted out both ways**.
Decimal odds include the stake in the payout: $1 on a fighter at 1.55 returns
$1.55 total — your dollar back plus **$0.55 of winnings**, and +$0.55 is what
the column shows. A loss is the whole stake gone: −$1.00. Sum every row and you
get exactly what's in your pocket.

Wins are usually under a dollar because the model's value bets are mostly
short-priced favourites (odds 1.2–1.6), where profit per dollar is small. Odds
above 2.00 — underdogs — pay more than the stake. This asymmetry is also why a
55.9% hit rate only makes +6.1% ROI: the average win banks ~$0.40 while every
loss costs the full $1.00 (at odds 1.40 you need ~71% winners just to break
even, so 55.9% on bets priced to imply ~52% is a thin, real edge).

### What use is the Kelly size column in the History bet table?

It's the conviction column: the share of bankroll the staking discipline
would commit to that bet, scaled by how far the model's probability beats
the price (capped at 25%). It distinguishes a maximum-conviction bet (25%)
from a technically-value-but-barely one (0.1%) that flat P/L treats as
equals, and it reconciles the two ROI numbers: flat ROI weights all bets
equally, Kelly ROI weights by this column. Kelly ROI running *above* flat
ROI means the model's highest-conviction bets have been its most profitable
— evidence the probabilities are informative, not just directionally right.
(The P/L column itself is flat-$1, so Kelly size is context rather than
row-level accounting.)

### Is the hit rate computed over all fights, or just the bets placed?

Just the bets placed: `bets won / bets placed` (voids excluded). Rule A's
55.9% means 55.9% of its 4,536 placed bets won — the ~1,250 fights it
declined don't enter the calculation at all; they only show in the *bet
rate* column. This is also why a lower hit rate can coexist with higher
ROI — and why "fewer bets" does NOT mean "higher hit rate", which was worth
verifying numerically. Selectivity here filters for bigger *edge*, not
likelier winners, and big edges live at longer odds: C's median bet is at
2.15 (47% implied) vs A's 1.93, and the 1,248 bets A places but C drops are
short-odds favourites (median 1.52) winning 59.4% — C throws away precisely
the high-hit, low-payoff bets. The benchmark that actually matters travels with the bets: a price *is* a
predicted win rate (win exactly `1/odds` of the time and you break even —
at 1.93, winning 51.8% exactly cancels gains against losses), so the
question is never "did I win a lot?" but "did I win more than the odds
said I would?". A won 55.9% of bets the market priced at 53.0% (+2.9pp
above fair); C won 54.6% of bets priced at just 49.9% (+4.7pp). C beats
its own benchmark by more — that's why it earns more per bet despite the
lower absolute hit rate. Comparing raw hit rates across rules is comparing
scores on two different exams. (The dashboard's replay-summary column header originally read
just "Hit" — it says "Hit rate" now.)

### Where does "implied probability" come from?

From the odds themselves — no external data. Raw implied probability is
`1/odds` (1.93 → 51.8%): the win rate at which the price is fair to you, so
beating it is the break-even test. The two sides of a fight sum to ~105%,
the excess being the bookmaker's margin (vig). The **vig-free** version
normalizes the pair to 100% — `(1/odds_r) / (1/odds_r + 1/odds_b)` — giving
the market's actual belief; it's what rule E shrinks toward and what the
model's `market_prob` feature is built from. Odds sources: historical
closing odds (BestFightOdds via the mma-ai dataset, median across books)
for the replay and training; Sportsbet (staking) + de-vigged AU-median
(feature input) for the live weekly card.

### Walk me through one row of the History bet table

Take: `2025-10-04 · Jiri Prochazka over Khalil Rountree Jr. · 1.55 · 64.5%
· 17.0% · +$0.55 · +$0.09 · won`.

The rule backed Prochazka at closing odds **1.55** ($1 returns $1.55 on a
win). **Market win % 64.5** is that price as a probability (`1/1.55`) — the
market's rating of Prochazka, and the exact win rate where the bet breaks
even. **Kelly size 17.0%** is the stake the Kelly formula sets from how far
the model's probability sits above 64.5% — run backwards, 17% at 1.55
implies the model had him at ~70.5%, so the column measures the
model–market disagreement (tiny edge → 1–2%, huge edge → the 25% cap).
He **won**, so: **flat P/L +$0.55** (staked the whole $1, kept odds−1),
**Kelly P/L +$0.09** (staked only 17¢, kept 17¢ × 0.55). The 0.55 in both
is the *profit rate of the odds*: $1 at 1.55 returns $1.55 = your $1 back
plus $0.55 winnings, so `odds − 1` is profit per dollar staked and any
win's profit is `stake × (odds − 1)` — the flat and Kelly columns just
expose different stakes to the same rate. One sentence:
market said 64.5%, model said ~70.5%, the 6-point gap justified a 17%
stake, and the win paid 55¢ per flat dollar or 9¢ per Kelly dollar.

### Does the History replay skip no-value fights, the way the live rule does?

Yes — the replay and the weekly job share the same condition (and the same
code, `predict.py:kelly_edge`): a bet is placed only when the model's win
probability **exceeds** the odds-implied probability (`p × odds − 1 > 0`,
i.e. `p > 1/odds`), and skipped when neither side clears it. The Replay
summary's *bet rate* column shows the discipline: rule A staked only 78% of
the 5,786 fights — the rest are the historical equivalent of the weekly
"$0 (no value)" rows — and C's vig floor bets just 57%. So the replayed ROI
is the return on the bets the rule would actually have placed, not on
blanket-betting every fight.

The bet table itself lists **only placed bets** — skipped fights carry no
stake or P/L, so they'd be empty rows. The passes show up in the aggregates
instead: the fights-with-odds tile (5,786) vs rule A bets (4,536), and the
bet-rate column. Passing on a fight is the rule working, and every skipped
fight was still evaluated.

### Why C, E, F — what happened to B and D?

Entry 9 pre-registered five candidate rules, A through E, on the same
5,786-fight backtest. Only three survived to become named, tracked rules;
B and D were tried and **rejected outright** at that same decision point,
which is why the trial reads A/C/E/F instead of A/B/C/D:

- **B ("carve-out")** — rule A minus one specific losing segment
  (near-coin-flip fights, `|p−0.5| ≤ 0.10`, where the market was already
  one-sided, `≥ 0.65`). Looked promising on the full pool (+15.0% Kelly
  vs A's +14.0%), but the gain came entirely from the first half of the
  data and had vanished by the second (H2 Kelly +4.7% vs A's +4.8% — no
  real edge left). Rejected: the pre-registered bar required beating A on
  **both halves**, not just the pooled average, precisely to catch a
  segment cut that only worked in hindsight.
- **D ("never-fade")** — C's vig-floor filter, further restricted to only
  bet the market's own favourite, never fade it. Its hit rate looked
  spectacular (72.8%!) but that's the tell, not the win: restricting to
  favourites inflates hit rate mechanically while gutting the payoff per
  win, and its Kelly ROI (+10.4%) was the **worst of all five** candidates
  — confirmed by a preview the entry ran *before* scoring D, predicting
  exactly this failure from the direction split. Rejected outright, no
  ambiguity.

So B failed the "robust across time" test and D failed on raw numbers —
neither one was close enough to be worth a live shadow slot. C and E
passed the closer call (strong pooled numbers, one borderline half) and
earned the prospective trial; F (entry 10) was added later as the fitted
version of E's idea. The letters name the original five-arm registration,
not a "rules so far" count — that's why the surviving three aren't
relettered A/B/C.

### What are shadow rules C, E and F, and why are they logged but not staked?

Entry 9 backtested five staking rules on 5,786 historical fights. Rule A won on the
pre-registered criteria, but two losers looked suspiciously good:

- **C ("vig floor")** — A, but an edge must exceed that fight's bookmaker margin
  (the vig, typically ~5–6%): edges smaller than the margin are treated as noise.
  Fewer, more selective bets.
- **E ("shrunk staking")** — average the model's probability 50/50 with the
  market's vig-free implied probability *before* computing edge and stakes. Only
  bets where value survives conceding the market is half right; tames Kelly's
  oversized stakes exactly where the model disagrees hardest with the market.

A third shadow, **F ("fitted blend", entry 10, added Aug 16)**, blends the
model's probability with the market's in log-odds space at a fitted,
frozen trust weight (λ = 0.746) before betting — the measured version of
E's fixed 50/50; its 10-event clock starts from its first logged card.

Both C and E beat A on parts of the backtest (E's Kelly ROI was +27.9% vs A's +14.0%, and
both held up better in the most recent half of the data, where A's edge collapsed
to +0.9% flat), but neither met the pre-registered promotion bar — and the best of
five candidates on the *same dataset used to choose* is exactly where the winner's
curse bites. So instead of guessing, every weekly card logs C's and E's hypothetical
splits alongside A's real one, and genuinely held-out results adjudicate.

On UFC 330 all three agreed Donte Johnson was the strongest edge but differed on
sizing: A spread $50 over four bets ($22 on Johnson); C and E each concentrated the
full $50 on Johnson alone — his 6.8% edge was the only one to clear C's 5.9% vig
floor, and the only one still positive after E's shrink (76.3% → 71.9%, and
.719 × 1.40 = 1.006).

### How did the four rules differ on an actual card? (UFC 330, Aug 2026)

Same card, same model, four disciplines: **A** spread $50 over four edges
($6 Makhachev, $16 Alvarez, $22 D. Johnson, $6 Magny), **C and E** each
put all $50 on Donte Johnson (the only edge clearing their filters), **F**
split $50 over three ($17 Alvarez, $29 Johnson, $4 Magny). Johnson won by
first-round KO; Alvarez lost. Outcome: A won 3 of 4 bets yet finished at
**$49.98** — thin favourite edges pay pennies and one loss erased them —
while C and E returned **$70.00** (+$20) and F **$48.24** (−$1.76), dinged
by its diluted Alvarez position. Humility beat diversification on this
card; one card proves nothing, which is why the trial runs ten.

### What if we combined the best-hit-rate rule with the most-profitable rule?

Tested on the 5,786-fight pool (23 Aug 2026). The literal combination —
D's selection (best hit rate, 72.8%) with E's shrunk sizing — and the
delta version — C's selection (best hit&minus;market delta) with E's
sizing:

| Arm | Bets | Hit | Mkt avg | Delta | Flat ROI | Kelly ROI | H2 kelly |
|---|---|---|---|---|---|---|---|
| D (best hit) | 1,414 | 72.8% | 68.4% | +4.4pp | +6.4% | +10.4% | +4.4% |
| E (most profit) | 3,340 | 54.6% | 50.1% | +4.6pp | +9.2% | +27.9% | +23.8% |
| G = D sel + E sizing | 1,408 | 72.9% | 68.5% | +4.5pp | +6.6% | +20.5% | +13.1% |
| CE = C sel + E sizing | 3,282 | 54.6% | 49.9% | +4.8pp | +9.5% | +28.0% | +24.5% |

Findings: (1) grafting E's sizing onto D doubles D's kelly ROI, but G
still loses to plain E — **D's high hit rate isn't better betting**; its
bets average 68.4% market-implied, so the delta (+4.4pp) matches C/E's,
and restricting to market-agreeing favourites discards ~60% of the
profitable pool. Hit rate is cosmetic; delta is the profit source. (2)
The delta version (CE) tops every column — but only by +0.1 to +0.7pp
over plain E, because C and E already select nearly identical bets: **E
effectively is this combination** (its shrink filters and sizes at
once). A margin that thin from stapling backtest-best components is
winner's-curse bait, so no fifth shadow rule was added; revisit if the
shadow logs ever show C and E disagreeing materially on live cards.

### What's "H2 kelly" in these tables?

H2 = the second, more recent half of the backtest history (bets sorted by
date, split at the median; H1 is the older half), and "H2 kelly" is the
kelly-staked ROI on just those recent bets. It exists because a
whole-history average can hide a dying edge as markets sharpen &mdash;
and it's decisive here: rule A's whole-history flat ROI is +6.1% but its
H2 flat is +0.9% (the edge nearly evaporated recently), while C and E
hold +7&ndash;8% in H2. That gap, more than the headline numbers, is why
C/E earned the live trial. Entry 9's promotability bar required beating A
in both halves under both staking schemes; none did, hence the trial.

### How does a shadow rule get promoted to the real rule?

Pre-registered in entry 9, before any card was scored: **after 10 logged events, a
shadow rule replaces A only if it beats A on cumulative bankroll-replay return AND
was ahead on at least 6 of the 10 cards.** Otherwise A stands. The Friday scoring
job maintains the running tally in `ledger.md` on the `weekly-predictions-log`
branch. The criterion is fixed in advance so the outcome can't be gamed by picking
a flattering stopping point.

### What happens when a fight changes after predictions are posted?

It's a **void** — treated as no-bet, stake returned, in all three rules. A late
replacement opponent means the logged prediction and odds describe a fight that
never happened (e.g. UFC 330's Charles Johnson bout, where Ochoa was replaced by
Henrique after prediction: the model had priced Ochoa, so the bout is void even
though Johnson still fought). Cancelled bouts are voids too. `scripts/score_card.py`
takes voids explicitly in its `results.json` input.

---

## Model & training

### Why don't we retrain every week?

Deliberate design (entry 5 redesign). What a weekly retrain would add is almost
nothing: ~12 fights on ~8,000 training rows (a 0.15% change) — the learned patterns
don't move. What it would cost:

- **It's a multi-hour, fragile run** (rolling-window grid search + 100 Optuna
  trials). Cloud containers are reclaimed at ~8h regardless of activity; two full
  runs were lost to this. An unattended weekly retrain gambles against that clock.
- **Silent odds-blind regression.** The model trains on historical odds;
  `odds_train.csv` must be rebuilt before every retrain (HuggingFace download +
  `pg_restore`). If that step fails the pipeline doesn't error — it quietly trains
  an odds-blind model, undoing entry 5. Unattended automation is where that hides.
- **It breaks the experiment discipline.** The protocol is one variable per run,
  McNemar against a snapshotted baseline. A model that changes weekly has no
  stable baseline.
- **It corrupts the live bet trial.** The 10-event A/C/E comparison tests staking
  rules *holding the model fixed*; retrain weekly and the tally grades ten
  different models.

The one real cost of not retraining — `fighter_history.parquet` staleness (a
fighter's newest results missing from their features) — is small in practice, since
most fighters on a card last fought 3+ months ago. It argues for a *deliberate*
retrain every month or two, not an automatic weekly one.

So the rhythm is: **predict weekly, score weekly, retrain occasionally and on
purpose** — via `scripts/weekly_pipeline.sh`, with the Optuna resume protection and
a proper EXPERIMENTS.md entry, ideally at natural boundaries like the end of the
10-event trial.

### Why is "beat the market" the goal instead of prediction accuracy?

Because the market is the actual opponent. Entries 1–2 measured the bar: closing
favourites win 66.3% with log-loss 0.6089; a model that "predicts well" in a vacuum
but sits behind that loses money on every bet defined by disagreeing with the
market (the close-vs-onesided segment ran −9.5% ROI). Every experiment is therefore
judged by `scripts/odds_backtest.py` against the market baseline — accuracy vs the
favourite-wins rate, log-loss vs the vig-free market log-loss, and dollar ROI —
not against a coin flip.

---

## Operations

### What runs when? / How does the whole pipeline fit together?

**Modeling pipeline** (`ufc_prediction_claude.ipynb`) is manual, never triggered
by a Routine — it needs historical odds data that isn't safe to fetch from the
cloud, so retraining is deliberately not automatic. Order: load committed raw
CSVs → clean/merge → feature engineering (prior-fights-only, mirrored to kill
red-corner bias) → rolling-window walk-forward CV + Optuna tuning → chronological
holdout (validation slice tunes the blend, test slice scored once) → ensemble
(top-3 XGBoost + LightGBM + CatBoost, logistic-stacked on pooled OOF) → fixed
0.5 threshold → export `ensemble.joblib` + `fighter_history.parquet`. `predict.py`
replays the same feature math against those two artifacts to serve a single
fight — that's what both weekly Routines and the Streamlit app call, no
retraining needed.

**Two cloud Routines, both AEST, no PC involved:**

- **`ufc-weekly-card-day`, Thursday 1 PM (`0 3 * * 4` UTC):** cheap ufcstats
  probe (usually blocked, skips gracefully) → WebSearch the next card → build/
  refresh `card.json` odds via `scripts/fetch_card_odds.py` (Sportsbet staking
  price + de-vigged AU-median feature price) → `send_weekly_predictions.py`
  (rule A's real $50 stakes + C/E/F shadow logs) → commit
  `predictions_output.md` + `card.json` to `weekly-predictions-log` → rebuild +
  republish the dashboard → phone notification with the slip.
- **`ufc-friday-scoring`, Friday (`0 8 * * 5` UTC ≈ 6 PM AEST):** find the most
  recent completed-but-unscored card → WebSearch results (voids for changed
  fights) → `scripts/score_card.py` grades A/C/E/F → append `ledger.md` +
  `collected_odds.csv` on the log branch → rebuild `odds_train.csv` for the
  History tab's backtest (mma-ai dump, gitignored, never committed) → rebuild +
  republish the dashboard → phone notification with the result and the running
  promotion tally.

- **`ufc-monthly-research`, 1st of the month (`0 3 1 * *` UTC = 1 PM AEST,
  added 21 Aug 2026):** deep research sweep — recent classification/tabular ML
  methods, sports-prediction and betting-market literature, UFC news that
  changes the data-generating process (rules, judging, divisions), and
  candidate new stats/data sources → dated entry in `docs/RESEARCH_LOG.md`
  with a verdict per idea → judgement call: at most one retrain-worthy change
  (executed under the full experiment protocol and delivered as a PR Michael
  merges — never straight to master), or an explicit "no change warranted",
  the expected outcome most months. Ideas already tried and rejected in
  `EXPERIMENTS.md` can't be re-proposed without new evidence.

All Routines share the git-safety pattern (`git show`, or checkout immediately
followed by `git restore --staged`); the two weekly ones never touch the
modeling notebook or commit odds/mma-ai data, and the monthly one may retrain
only under the experiment protocol above.

**Retraining** outside the monthly Routine's gated path is manual:
`scripts/weekly_pipeline.sh` on a GPU machine —
fetches training odds (mma-ai HuggingFace dump via `pg_restore`, never
committed), scrapes fresh data from the sibling `UFC-Predictions` repo,
retrains with Optuna's resume mechanism (survives the cloud's ~8hr container
reclaim), commits the model artifacts. One variable per run, gated by
`EXPERIMENTS.md`'s McNemar/market-comparison protocol.

A third trigger, "UFC weekly retrain + predictions (fires Fri 9AM AEST)", was
a leftover from before the Aug 2026 redesign split retraining out of the
weekly job (found stale via `list_triggers` on 2026-08-21, `next_run_at`
already in the past) — confirmed dead and deleted the same day.

### An event just finished — why doesn't the dashboard show it yet?

The trial tables read `ledger.md`, which is written only when the card is
*officially scored* (`scripts/score_card.py`, run by the Friday Routine) —
not when the fights end. Between the event and its scoring run the
dashboard correctly shows the pre-event state. Scoring can be run early by
hand when results are in (UFC 330 was scored the Sunday it finished, at
Michael's request); the Friday run then finds nothing left to score.

### Why is a card scored 5–6 days after it happens?

Cards run Saturday night US time — Sunday afternoon AEST — and the scoring Routine
runs Friday 6 PM AEST, so each card is graded the following Friday. Nothing decays
in the meantime (results are results), it just means the scoring notification isn't
same-weekend. Moving scoring to Sunday evening AEST would grade same-weekend if
that ever matters more than the Friday rhythm.

### What's the difference between the Performance and Experiments tabs?

**Performance** is the money view: a profit/loss-so-far tile (rule A,
real money), a rule-A-only chart, a bankroll allocator for the upcoming
card, and every past event listed with its net — click one open for the
per-fight detail. **Experiments** is the research view: the rule
explainer up top, a rule A/C/E/F chart, the live comparison table, and
the backtest reference. Both charts share one engine and a metric
dropdown — net return, hit rate, bet rate, avg market win% — see the next
entry. (Performance held the trajectory material itself until Aug 17,
when that moved into Experiments; the standalone Promotion trial 10-slot
strip was removed the same day — its criterion text lives in the top
explainer and its live tally is the comparison table's "cards ahead of A"
column, so the strip was pure redundancy.)

### What do the chart's metric options (net / hit rate / bet rate / avg market win%) show?

Every line chart in the dashboard (Performance, Experiments, and
History's backtest replay) shares one engine with a dropdown that
switches what's plotted, always as a running total to date — never two
metrics on one axis at once. **Net return ($)** is cumulative profit, the
default. **Hit rate (%)** is cumulative wins &divide; cumulative bets
placed. **Bet rate (%)** is cumulative bets placed &divide; cumulative
fights offered — how often that rule finds value at all. **Avg market
win (%)** is the average odds-implied probability of that rule's own
bets to date (`100/odds`, from the same `shadow` strings
`scripts/score_card.py` grades) — higher means shorter-priced, safer
picks; lower means it's finding value in bigger disagreements with the
market.

The **Experiments** chart briefly carried a flat-$1 net option (Aug
2026, to strip out stake concentration) but it's since been removed at
Michael's request — that chart now plots real-$50 net only, matching the
Rule comparison table and the promotion decision; flat-$1 tracking still
lives in `ledger.md`'s last column and the History tab. **Performance**'s
rule-A chart keeps real dollars throughout, since that's what's actually
staked. Marker size always reflects that event's real $ swing regardless
of which metric is on screen, and hovering (or clicking to pin) a point
shows all the numbers together no matter which one is plotted.

### In the tooltip, why does a rule's hit rate differ from its avg market win — did it disagree with the market?

They're **outcome vs price** for the same bets, not two opinions about
who wins. Hit rate = fraction of that rule's bets that won; avg market
win = the average odds-implied probability (`100/odds`) of those same
bets — what the prices "promised." Hernandez card example for E: hit 67%
(2 of 3 won) vs market 64.6% (Padilla @2.01 &rarr; 49.8%, de Ridder
@1.25 &rarr; 80.0%, Hernandez @1.56 &rarr; 64.1%, mean 64.6%). The ~2pp
gap means E's picks won slightly more often than the odds predicted —
that gap IS the per-bet profit signal (it matches the +$0.26 flat net),
and it can coexist with a real-$ loss when the sizing puts the biggest
stake on the loser, as it did here. As for disagreement: every bet is
definitionally a small disagreement with the price (no perceived
mispricing &rarr; no bet); on this card no rule faded a market
favourite, and all four bet the same three fights, so their hit/market
numbers were identical — only stake splits differed.

### Why is the flat ROI so much higher than the staked ROI (or vice versa)?

The two ROIs differ through exactly one thing: whether the big-stake bets
did better or worse than the average bet. Flat weights every bet equally;
staked ROI is a weighted average where the confident (big-kelly) bets
count more, so the gap between them measures where the confidence went.
Live example (after 2 events): rule A is +12% flat but &minus;5.4% real,
because kelly put the largest stakes on exactly the bets that lost ($16
Alvarez, $21 Hernandez) while the winners carried small stakes. Over the
5,786-fight backtest it inverts &mdash; every rule's kelly ROI beats its
flat ROI (A +14.0% vs +6.1%) &mdash; meaning bigger model edges really did
earn better-than-average returns there, which is the only thing that
makes kelly sizing worth using. At n=2 the live inversion is noise;
if flat were still beating staked after many events, that would be a real
finding (probabilities rank winners fine but mis-rank their own
confidence) and flat staking or a tighter kelly cap would deserve a look
as its own rule.

### Are Kelly and flat both staking $1?

No. Flat is literally $1 on every bet. Kelly-staked is a *variable*
stake &mdash; the bet's kelly fraction of the same $1 bankroll-unit
(non-compounding; convention changed from a $100 notional to $1 on
23 Aug 2026 so both views share one base): a thin-edge k=0.02 bet stakes
2&cent;, a capped k=0.25 bet stakes 25&cent;. Two consequences. (1) The
**ROIs are directly comparable** &mdash; ROI divides profit by dollars
staked, so the notional cancels; the ROI gap isolates purely whether
confidence-weighting helped. (2) The **cumulative-$ lines still aren't on
the same staked base** &mdash; kelly stakes ~9&times; fewer dollars than
flat over the same bets, so its dollar curve runs lower even at higher
ROI. The Replay summary table now shows both P/L columns and both ROIs
side by side (hover the Kelly P/L for total dollars staked). Same
structure on the live side: "real" is the $50-per-event bankroll split,
"flat" is $1/bet.

### Did the $100&rarr;$1 notional change actually make sense?

Yes, as a pure presentational rescale: the per-bet table already used
kelly-of-$1, so the chart's $100 was an internal inconsistency (and the
direct cause of the "$100 per event?!" misreading), and both views now
share one bankroll-unit &mdash; flat risks the whole $1, kelly the kelly
share of it. Nothing analytical moved: curve shape, every ROI, and every
conclusion are identical (a notional is an arbitrary multiplier). The
trade-off: kelly's dollar values are now small (2025 reads +$0.37) and
its line generally sits *below* flat's &mdash; not worse performance,
just ~9&times; fewer dollars staked; dollars-on-one-axis always privileges
one staking base, so cross-convention judgment belongs to the summary
table's ROI columns and the chart is for trajectory. If the sub-dollar
axis grates, the next option is normalizing kelly stakes to average $1
&mdash; fudgier to explain, so only if the cents actually bother in
practice.

### How do I compare flat vs kelly apples-to-apples?

**Use the ROI columns in the Replay summary table** &mdash; ROI divides
each convention's profit by the dollars it actually risked, so the
stake-size difference cancels entirely (2025: flat +6.9% vs kelly +1.8%;
that IS the fair comparison). The dollar curves can never be made fair
by inspection, because deploying different amounts of capital is the
strategy itself, not a distortion. If comparable *curves* are ever
wanted, the one honest construction is rescaling kelly's stakes so its
average stake is $1 (stake = k &divide; mean k, proportions preserved)
&mdash; both conventions then deploy the same total capital and the two
lines answer "given the same money, does confidence-weighting allocate
it better?" Not implemented (deliberately): it would be a third staking
convention whose numbers match neither the summary table nor the per-bet
table, recreating the cross-surface inconsistency the $1 rescale just
fixed. If adopted later, it should *replace* the kelly-of-$1 chart view
and relabel the summary column with it, not sit alongside.

### So kelly betting "$100 per event" through 2025 only made $36?

No $100 was ever staked per event &mdash; that's the notional the kelly
*fraction* applies to, per bet. The actual 2025 numbers behind the chart's
+$36.71 end label: 181 bets Jan&ndash;Oct (the odds data ends in October),
$2,033 total staked at an average $11.23/bet (max $25, the 0.25 kelly
cap), net +$36.71 = **+1.8% ROI for 2025**. Read it as "risking ~$2,000
across the year in ~$11 nibbles returned $37," not "$100 a card returned
$37." The honest part the low number does reveal: 2025 was genuinely
mediocre for rule A even correctly read &mdash; consistent with entry 9's
finding that A's edge collapses in recent data (recent-half flat ROI
+0.9% vs +11.3% earlier). The +14% kelly-ROI headline is a whole-history
average leaning on older, easier years, which is exactly why C and E
(recent-half +7&ndash;8%) earned their live shadow trial. (Since 23 Aug
2026 the chart's kelly notional is $1 rather than $100, so this same 2025
view now reads +$0.37 on ~$20 staked &mdash; identical ROI, smaller
unit.)

### Why did the kelly-staked view average ~$11 a bet?

(Figures below are at the pre-23-Aug-2026 $100 notional; at today's $1
notional divide by 100 &mdash; the fractions and the logic are
unchanged.) Nobody chose it &mdash; it's emergent from `k = (p&middot;o&minus;1)/(o&minus;1)`
applied to whatever edges the model found (2025: median stake ~$10, 55
bets under $5, 32 at $15&ndash;25, 26 pinned at the $25 cap). The average
sits that high because of the formula's denominator: **short-priced
favourites generate big kelly fractions from modest edges**. Model 82% at
odds 1.30 &rarr; EV edge 0.066, k = 0.066/0.30 = 0.22 &rarr; $22; model
40% at odds 2.80 &rarr; EV edge 0.12 (nearly double), k = 0.12/1.80 =
0.067 &rarr; $7. Same-ballpark edges, 3&times; different stakes &mdash;
deliberate, not a bug: kelly stakes more where variance is lower (a 1.30
favourite usually wins, so more can be risked per unit of edge without
ruin risk); 2025 favourites (&le;1.5) averaged k=0.139 vs underdogs
(&gt;2.5) at 0.038. It's also exactly the behaviour rule E challenges:
the biggest stakes land where the model most confidently disagrees with
the market on favourites, and misplaced confidence there concentrates
the damage (Alvarez/Hernandez live). The 0.25 cap is the guardrail.

### Decode the kelly-staked chart's subtitle for me

Phrase by phrase. *"Each bet staking its kelly fraction of a fixed $1"*
(a $100 notional until 23 Aug 2026; rescaled so flat and kelly share one
base): walk up to every bet with a fresh $1; the kelly formula names a
percentage of it to risk (2% &rarr; 2&cent;, 22% &rarr; 22&cent;) &mdash;
"fixed" means the same fresh $1 every bet, never adjusted by results.
*"Non-compounding"*: winnings don't roll into bigger stakes and losses
don't shrink the next bet &mdash; textbook kelly compounds, but that's
switched off here (same reason the live trial uses fixed $50 tranches:
keeps every bet on equal footing, so the curve isn't path-dependent on
early luck). *"The backtest's analog of real staking"*: a hedge &mdash;
live rule A splits one $50 pot per card, but the backtest is a flat list
of bets with no card structure, so kelly-of-$100-per-bet is the closest
per-bet equivalent; both weight confident bets more. *"Pooled
out-of-fold fights"*: every replayed prediction came from a model that
never trained on that fight (walk-forward CV) &mdash; no memorized
answers. *"Matched to closing odds"*: each fight joined to its real
historical closing line; unmatched fights drop out, leaving the 5,786.
*"Upper bounds apply"*: every number is a ceiling &mdash; the replay
assumes you got the closing price (you'd really bet earlier at different
prices), no bet limits, no account restrictions, and that your money
never moves the line. Real results would be somewhat worse, which is why
the backtest only gates which rules get trialled while the live record
decides promotion.

### With flat $1/bet tracking, C is no longer ahead of A on the Experiments chart — did its edge disappear?

No — this is small-sample noise from having only one live event logged, not
a reversal of the backtest finding. UFC 330 (`ledger.md`'s only row so far):

| Rule | Bets | Real-$ net | Flat-$1 net |
|---|---|---|---|
| A | 4 | −$0.03 | +0.59 |
| C | 1 | +$20.00 | +0.40 |
| E | 1 | +$20.00 | +0.40 |
| F | 3 | −$1.76 | +0.31 |

C found value in only 1 of 11 fights that card and staked its whole $50
bankroll on it, which won at 1.40 odds — a big real-dollar swing from one
bet. A spread its $50 across 4 bets. Real dollars reward C's concentration;
flat $1/bet strips that out, and on a single bet each, C's +0.40 just
happens to land below A's four-bet +0.59.

The backtest that originally put C ahead (EXPERIMENTS.md entry 9, 5,786
pooled-OOF fights) is unaffected — C's flat ROI there is +9.4% vs A's
+6.1%, still the larger, less noisy sample. The pre-registered promotion
criterion needs 10 logged events before deciding anything, specifically
because one event's bet count is this volatile, and even then it's judged
on real-$ bankroll replay (the Rule comparison table), not the flat chart.

**Full per-bet math.** UFC 330's 4 staked results: Makhachev won, Alvarez
lost, Donte Johnson won, Magny won.

Rule A (4 bets, $50 total):

| Bet | Stake | Odds | Result | Real return | Flat contribution |
|---|---|---|---|---|---|
| Makhachev | $6 | 1.286 | win | 6&times;1.286=$7.72 | +0.286 |
| Alvarez | $16 | 1.39 | loss | $0 | &minus;1 |
| Donte Johnson | $22 | 1.40 | win | 22&times;1.40=$30.80 | +0.400 |
| Magny | $6 | 1.909 | win | 6&times;1.909=$11.45 | +0.909 |
| **Total** | $50 | | 3/4 won | **$49.97** &rarr; net &minus;$0.03 | 0.286&minus;1+0.400+0.909 = **+0.59** |

Rule C/E (1 bet each, both picked Donte Johnson $50 @1.40, won): real
50&times;1.40=$70.00 (net +$20.00); flat just that one bet, 1.40&minus;1 =
**+0.40**.

Rule F (3 bets, $50 total &mdash; Alvarez $17@1.39, Donte Johnson $29@1.40,
Magny $4@1.91):

| Bet | Stake | Odds | Result | Real return | Flat contribution |
|---|---|---|---|---|---|
| Alvarez | $17 | 1.39 | loss | $0 | &minus;1 |
| Donte Johnson | $29 | 1.40 | win | 29&times;1.40=$40.60 | +0.400 |
| Magny | $4 | 1.909 | win | 4&times;1.909=$7.64 | +0.909 |
| **Total** | $50 | | 2/3 won | **$48.24** &rarr; net &minus;$1.76 | &minus;1+0.400+0.909 = **+0.31** |

The flat column is "sum of (odds&minus;1) per win, &minus;1 per loss" &mdash;
it ignores stake size, so C/E's one big real-dollar win ($20) carries the
same weight as any other single winning bet (+0.40), while A's four smaller
bets accumulate to +0.59 even after eating a full &minus;1 on the Alvarez
loss.

**Why $1-flat and $50-real can even land on different signs.** Both totals
are the same sum of the same per-bet outcomes, just weighted differently.
Define each bet's outcome per $1 staked as `outcome_i = odds_i&minus;1` on a
win, `&minus;1` on a loss. Then:

    real_net = &Sigma; s_i &middot; outcome_i,   where &Sigma; s_i = $50 (Kelly-proportional stakes)
    flat_net = &Sigma; 1 &middot; outcome_i = &Sigma; outcome_i          ($1 on every bet)

The two formulas sum the *identical* win/loss outcomes; only the weight
`s_i` (Kelly stake) vs. `1` (flat) differs. For rule A's 4 bets ($6, $16,
$22, $6 &mdash; summing to $50):

    real_net = 6(0.286) + 16(&minus;1) + 22(0.400) + 6(0.909) = 1.716&minus;16+8.800+5.454 = &minus;0.03
    flat_net = 1(0.286) + 1(&minus;1) + 1(0.400) + 1(0.909) = 0.286&minus;1+0.400+0.909 = +0.59

The Alvarez loss got 32% of the real bankroll ($16/$50, Kelly-sized up
because the model disagreed hardest with the market there) but only 25%
weight ($1/$4) under flat &mdash; real dollars over-weighted the one loss
relative to flat, flipping the sign. Rules C/E, with only 1 bet each,
can't diverge this way: `real_net = 50&times;0.400 = $20` and
`flat_net = 1&times;0.400 = $0.40` are the same 40% return scaled by a
different total, since there's nothing to weight differently with a single
bet. Divergence only appears once a rule has &ge;2 bets in a period, and
only when its Kelly allocation and its win/loss pattern don't line up the
same way flat weighting would.

**Is it a problem that switching to flat-$1 changed which rule looks
ahead?** No &mdash; that's the change doing exactly what it was asked to do,
not a bug. There is no neutral way to rank "which rule is winning" across
strategies that bet different amounts on different picks; every weighting
convention embeds a choice. Flat-$1 was introduced specifically to strip
out stake-concentration inflation (C shoving its whole bankroll onto one
bet looking bigger than it should). Once that's stripped, C's one win no
longer outweighs A's four bets &mdash; that's the intended effect, not a side
effect. Two things keep it from mattering operationally: (1) it's one
event &mdash; A's +0.59 vs. C's +0.40 is a noise-sized gap that could flip on
the next card; (2) it doesn't touch the actual decision &mdash; the
pre-registered promotion criterion (entry 9) was locked to real-$ bankroll
replay before this chart existed, precisely so a presentation choice like
this can't quietly move the goalposts. Real-$ answers "how would my
bankroll actually have grown"; flat-$1 answers "bet-for-bet, ignoring how
much confidence each rule backed each pick with, who called it better."
Neither is "the truth" and they can legitimately disagree on small samples.

### What should I actually make the promotion decision off of?

The pre-registered criterion (entry 9, revised Aug 20), not whichever chart
currently looks most convincing: after 10 logged events, promote a shadow
rule (C/E/F) over A only if it beats A on **cumulative real-$
bankroll-replay return** *and* a one-sided **Wilcoxon signed-rank test** on
the paired per-event differences rejects "no systematic edge" at
&alpha;=0.10 (`scripts/promotion_test.py`; this replaced the original
"ahead on 6 of 10 cards" clause, which a zero-edge rule passed 37.7% of
the time by luck). The criterion was written down
and committed before any live result existed &mdash; precisely so that once
metrics start disagreeing (as real-$ and flat-$1 already do, at event 1),
there's no temptation to reach for whichever one currently flatters the
rule you're hoping wins. Using flat-$1 as the decision basis today, after
seeing it happens to favor A, would be exactly the after-the-fact
metric-shopping pre-registration exists to prevent. Keep the flat-$1 chart
as a **diagnostic** &mdash; it's genuinely useful for understanding *why* a
rule is ahead (confidence-weighting vs. pure pick quality) &mdash; but let
only the Rule comparison table's real-$ numbers count toward the actual
call, and don't make that call at all before 10 events: at N=1 neither
number is trustworthy regardless of which one you pick.

### If 10 events is statistically weak, how many would make it strong?

Depends entirely on how big the true edge is. The controlling quantity is
the effect size d = (true per-event $ edge over A) &divide; (event-to-event
SD of that difference, roughly $10&ndash;15 at $50 stakes). Simulated power
of our one-sided &alpha;=0.10 Wilcoxon:

| True edge (on $50/event) | d | Events for 80% power | Power at n=10 |
|---|---|---|---|
| ~$8/event (huge) | 0.7 | 10 | 77% |
| ~$6/event | 0.5 | 19 | 56% |
| ~$5/event | 0.4 | 30 | 45% |
| ~$3.50/event | 0.3 | 53 | 34% |
| ~$2.50/event (&asymp; backtest-sized C&ndash;A gap) | 0.2 | 119 | 23% |

So 10 events is only well-powered against a huge edge; the C-vs-A gap the
backtest actually measured (~$1.50&ndash;$2.50/event) would need **100+
events &mdash; about two years of weekly cards** &mdash; to confirm
prospectively. That's by design, not a flaw: the statistical weight lives
in the 5,786-fight backtest, where such gaps are measurable, and the
10-event forward trial is a **reality check** against winner's curse
(best-of-five-rules selection), implementation drift, and market change
&mdash; big enough to catch "this rule is a disaster live" and to require
the live record to point the same way as the backtest, never big enough to
certify a small edge on its own. If the trial itself should carry the
evidence, the options are: extend to ~30 events (&asymp;7 months, detects
~$5/event edges) or ~50 (a year, ~$3.50/event) &mdash; or keep 10 as the
gate and read promotion as "backtest evidence + live sanity check," which
is what entry 9 pre-registered.

### Explain the power test behind that table

Two mistakes are possible when the trial concludes. A **false positive**:
promoting a rule that's actually no better than A &mdash; the test's
&alpha;=0.10 controls this directly (a genuinely-no-better rule passes at
most 10% of the time). A **false negative**: the rule really is better,
but 10 noisy events don't show it clearly, so we wrongly keep A. **Power
is the probability of avoiding the second mistake**: if the edge is real,
how often does the test actually catch it? Power 80% means that across
100 hypothetical trials where the rule truly is better, the test fires in
~80 and misses in ~20.

Power depends only on the edge-to-noise ratio, the effect size
`d = (true average per-event edge) / (event-to-event SD of the
difference)`. A single event's C&minus;A difference swings &plusmn;$10&ndash;15
(one upset moves it hugely), so the test is listening for a steady
$2&ndash;3/event hum under that noise &mdash; d &asymp; 0.2, nearly
inaudible in 10 samples &mdash; while an $8/event hum (d &asymp; 0.7) is
loud enough. Averaging n events shrinks the noise by &radic;n, not n:
hearing a hum half as loud needs four times the events, which is why the
required-n column explodes as the assumed edge shrinks.

The table was computed by simulation matched to the real procedure: for
each (n, d), draw n fake per-event differences with true mean edge d (in
noise-SD units), run the same one-sided Wilcoxon at &alpha;=0.10 that
`scripts/promotion_test.py` runs, and record whether it fires; the firing
fraction over 4,000 repeats is the power. ("Power 0.45 at n=10, d=0.4"
literally means the test caught a true ~$5/event edge in 1,802 of 4,000
simulated trials and missed it in the rest.) The textbook formula
n &asymp; (z<sub>&alpha;</sub>+z<sub>power</sub>)&sup2;/d&sup2; (with a
~5% Wilcoxon-vs-t adjustment) gives the same numbers. One honest caveat:
the table's rows are assumptions &mdash; the true d is exactly what's
being tested &mdash; so power analysis can't say what *will* happen, only
what the design *could* detect. Its use is knowing the trial's limits
before results exist: a tripwire for large effects, not an instrument
that can certify a $2/event edge.

**Column-by-column** (using the middle row, ~$5/event | 0.4 | 30 | 45%,
as the running example):

- **True edge (on $50/event)** &mdash; the *hypothetical* long-run
  advantage over A that the row assumes, in dollars per event: "suppose C
  really is $5/event better on average" (a 10-point ROI advantage on $50
  stakes). Never directly observable &mdash; each row is a what-if.
- **d (effect size)** &mdash; column 1 divided by the event-to-event
  spread of the difference (&asymp;$12 here): 5/12 &asymp; 0.4. Converts
  dollars into signal-to-noise units, which is all detectability depends
  on &mdash; a $5 edge under $12 noise and a $50 edge under $120 noise are
  the same problem for the test.
- **Events for 80% power** &mdash; scored events needed so the
  &alpha;=0.10 Wilcoxon catches that row's edge at least 80% of the time
  if it's real (80% = the conventional "adequately powered" benchmark,
  an accepted 1-in-5 miss rate). $5 row: 30 events &asymp; 7 months.
  Grows much faster than the edge shrinks (halve the edge &rarr;
  quadruple the events; the &radic;n effect).
- **Power at n=10** &mdash; the same detection probability evaluated at
  the trial length we actually pre-registered. $5 row: 45% &mdash;
  slightly worse than a coin flip at proving a genuinely-$5-better rule.

The two right columns are one fact from opposite directions: fix power at
80% and ask "how many events?", or fix events at 10 and ask "how much
power?". The table's shape is the argument in miniature: a 10-event trial
reliably detects only top-row-sized effects, which is exactly the
sanity-check role entry 9 assigns it.

### What is d actually supposed to represent?

**How visible the edge is in a single event.** The division is the point:
a dollar amount alone can't determine detectability &mdash; a $5 edge
under $1 of week-to-week wobble would show C beating A by $4&ndash;6
every single card (obvious immediately), while the same $5 under $50 of
wobble is invisible for years. Dividing by the SD strips out the dollars
and leaves the signal-to-noise ratio, the only thing the statistics
depend on. Three readings of the same number:

1. **Fraction of one week's luck**: d = 0.4 means the true advantage is
   40% of a typical event-to-event swing &mdash; any single card is ~2.5
   parts luck to 1 part edge, which is why only averages can reveal it.
2. **How often the better rule wins the week**: for bell-shaped
   differences, a random single card shows the better rule ahead with
   probability &Phi;(d) &mdash; d = 0.2 &rarr; ~58%, d = 0.4 &rarr; ~66%,
   d = 0.7 &rarr; ~76%. A genuinely better rule at d = 0.2 loses the
   head-to-head 42 weeks in 100; that's what "weak signal" means
   physically.
3. **How fast averaging rescues you**: n events shrink the noise by
   &radic;n while the signal stays put, so effective visibility is
   d&middot;&radic;n; the test needs roughly d&middot;&radic;n &gtrsim;
   2.1, which rearranges into the table's n &asymp; 4.5/d&sup2; column.

Caution: d uses the SD of the *true* event-to-event distribution, not
the SD computed from the observed diffs &mdash; at 2 events that
estimate is itself mostly noise. The &asymp;$12 in the table is a
plausibility estimate of the underlying spread, which is why the rows
are scenarios rather than measurements.

### So do we want d to be small, for more certainty?

The other way around: we want d **big**. The intuition flip usually comes
from the denominator &mdash; small *noise* is indeed good, but small noise
makes the ratio d *larger*, not smaller. Both routes to a big d are good
news: a bigger true edge (more dollars, easier to detect) or more
consistent week-to-week results (the same edge shows through faster).
Big d = loud signal over quiet noise = the better rule visibly wins most
weeks = few events needed (the table's top row: d = 0.7 needs only 10).
Small d = whisper under static = the better rule loses the head-to-head
42 weeks in 100 = 119 events for confidence. Small d is the problem
case, not the goal &mdash; and the concern with our trial is exactly that
the realistic d here (~0.2) sits in the low-certainty regime.

### Isn't "77% power at n=10" saying we're 77% sure there's an $8 edge?

No &mdash; that flips the direction of the conditional, the single most
common misreading of power. The table says: **IF** the true edge is $8,
**THEN** the test would detect it 77% of the time
(power&nbsp;=&nbsp;P(detection&nbsp;|&nbsp;edge)). It does not say "given
the data, there's a 77% chance the edge is $8"
(P(edge&nbsp;|&nbsp;detection)). Power is a property of the detector,
computed before any data exists &mdash; like a smoke alarm that catches
77% of real fires and false-alarms 10% of the time: those two numbers
describe the alarm, not whether your house is burning. When it beeps, the
probability of an actual fire is a third number that also depends on how
often fires happen (the prior). Converting power into "how sure are we
now?" needs Bayes. Example with a 50/50 prior that C truly has a
d&asymp;0.7 edge: if the test fires,
P(edge&nbsp;|&nbsp;fired) = (0.5&times;0.77) / (0.5&times;0.77 +
0.5&times;0.10) &asymp; 89%; if it stays silent,
P(edge&nbsp;|&nbsp;silent) &asymp; 20%. Neither equals 77% &mdash;
power's role is upstream, setting *how much* a firing or silent test
should move your belief. That's also why low power is so insidious: at
n=10 and d=0.2 (power 23%), a silent test barely updates anything &mdash;
the trial can't hear, and not-hearing isn't evidence of absence.

### Should I keep betting the same fixed $50 each event, or scale it?

Keep it fixed at $50 for now. Two reasons. First, the promotion protocol
(entry 9) compares rules across the 10-event trial on **equal footing per
event** &mdash; if the stake instead compounded off a growing/shrinking
bankroll, later events would carry more or less weight in the cumulative-
return metric, undermining the same equal-weighting property that made
"ahead on 6 of 10 cards" a meaningful check in the first place. Second, the
model's edge over the market is still unproven and under active test
(2026 odds backtest: 61.2%/0.642 model vs. 66.3%/0.6089 closing favourites)
&mdash; compounding stakes amplifies variance on top of an edge that isn't
validated yet, which is the wrong time to size up. $50/event is explicitly
framed as a bounded maximum loss, not a fraction of how the bankroll
happens to be doing. Revisit this once the 10-event trial resolves and a
rule has a demonstrated real-$ edge; scaling to a genuinely growing
bankroll is a reasonable question then, not mid-trial.

### After a losing week, do I top the float back up to $50?

Yes &mdash; that's literally what "fixed $50 per event" means: each card
gets $50 of fresh risk regardless of last week's result; the money isn't
a self-contained pot that must survive on its own winnings. Topping up
~$5 after a &minus;$5 card is the system working as designed, and it is
**not** loss-chasing &mdash; chasing is *raising* stakes to win losses
back (martingale territory); holding the stake constant is the neutral,
disciplined option, while betting only what's left would be the
compounding-down path-dependence the trial deliberately excludes. Think
in the ledger's terms: not "the pot is down to $44.58" but "risking $50 a
week, cumulative net &minus;$5.42 so far." The real safety mechanism is
the known ceiling: 10 events &times; $50 = $500 worst case, agreed
upfront. If $50/week ever stops being *comfortable* (not merely
annoying), the right move is lowering the bankroll for all future events
&mdash; never skipping top-ups after losses specifically.

### Would a $500 rolling bankroll over the 10 events beat $50 per event?

Total exposure is the same ($500 either way); the difference is that a
rolling bankroll makes each event's stake depend on how the previous ones
went. There IS a real benefit in that design &mdash; it's how Kelly betting
is meant to work: stakes shrink automatically in a drawdown (three losing
cards at fixed $50 cost $150 regardless; a rolling bankroll would have been
cutting stakes as it fell) and compound after wins, which is growth-optimal
**under a known positive edge**. But it only pays once the edge is proven:
compounding amplifies whatever is really there, noise included, and
mid-trial it also breaks the equal-per-event weighting the promotion
comparison depends on (see the previous entry). One practical wrinkle too:
the current splitter risks the whole per-event budget across value bets,
so handing it $500 would risk up to $500 every card &mdash; true
bankroll-fraction Kelly is a different staking rule that would itself need
implementing and trialling. Verdict: fixed $50 tranches through the trial;
"rolling bankroll + true Kelly sizing" is the natural upgrade if a rule
earns promotion.

### Why do we always seem to bet on the headline fight?

The model doesn't know a fight is the headline &mdash; there's no
card-position input, and the Kelly value test is applied identically to
every fight. The pattern comes from two things. (1) **Survivorship through
the data filter**: a bet requires both fighters to have history in our data
and known category values, and prelims are where debutants and short-notice
imports live &mdash; on the Aug 22 Hernandez card, 4 of the 8 no-bet fights
were unpredictable exactly because of missing history or unseen
stance/weight-class values, all prelims. Main-card fighters are
established, so they always survive into the biddable pool: the headliner
isn't being picked, the prelims are being filtered out. (2) **Richer
history &rarr; stronger opinions**: long records give the model more signal
to disagree with the market on, so established fighters clear the value
threshold more often. It's also not "the headliner gets the money": at
UFC 330 the main event got the smallest bet ($6 Makhachev) while a prelim
got the biggest ($22 Donte Johnson) &mdash; and two cards is a small sample
for reading a pattern at all.

### How much am I betting this week / what's the current slip?

Always $50 per event (fixed through the 10-event trial — see the stake-sizing
entry above), split across whatever the model finds value in. The current
week's exact slip lives in two places, both refreshed by Thursday's card-day
Routine: the dashboard's **Performance tab → upcoming card** (with the
bankroll allocator and the total-if-all-win row), and
`predictions_output.md` on the `weekly-predictions-log` branch (the "Your
bet" column). Worked example — Hernandez vs. Rodrigues, Aug 22 2026: $11
Padilla @2.01, $18 de Ridder @1.25, $21 Hernandez @1.56; max loss $50,
~$77 back (+$27) if all three win.

### Where do I see how the bets are going?

The **Octagon Ledger dashboard**:
<https://claude.ai/code/artifact/5d7c8637-557d-4ec2-981c-9255b986f52f> — a
Performance tab (money view: P/L so far, rule-A chart, bankroll allocator,
past-events detail) and an Experiments tab (rule comparison, chart, and
backtest reference) with these docs as the other tabs. It is generated by
`scripts/build_dashboard.py` from `ledger.md`; the Friday scoring Routine
rebuilds and republishes it right after grading each card, so it is always
current as of the most recent scored event.

### How do I open the dashboard on my phone?

Open the artifact URL above in your phone's browser while signed in to
claude.ai — it's a normal (private) web page, so it renders for your account
only unless shared from the page's share menu. Then **Add to Home Screen**
(Chrome: &#8942; menu &rarr; Add to Home screen; Safari: share icon &rarr; Add
to Home Screen) to pin it like an app; the same URL always serves the latest
published version since the Routines republish in place. Lost the link? The
gallery at <https://claude.ai/code/artifacts> lists everything you own —
the Octagon Ledger is the 🥊 one.

### Do any betting apps have an API that lets me place bets programmatically?

Retail bookmakers (Sportsbet, TAB, Ladbrokes, Neds, Bet365): **no** — no
public bet-placement API for individuals, and their terms prohibit
automation; scripted accounts get restricted or closed. The one real
exception is **Betfair**, an exchange rather than a bookmaker: its Exchange
API (API-NG) openly supports programmatic bet placement/cancellation, with
a free delayed app key for development and a live key on request — Betfair
AU even publishes automation tutorials. Caveats before wiring this project
to it: (1) the pipeline's edges are computed against Sportsbet fixed odds,
and Betfair takes ~5&ndash;8% commission on net winnings, so edges must be
re-derived net of commission; (2) MMA prelim markets on Betfair AU are
thin, so small value bets may not get matched at the modelled price;
(3) AU accounts can't bet in-play via the API (pre-fight only — which is
all this project does); (4) most importantly, automation is pointless
until the 10-event trial demonstrates a real edge — automating placement
before then just automates losing faster. Revisit if a rule is promoted.

### Where does the odds API key live, and where do I get one?

`ODDS_API_KEY` is set in the **cloud environment settings**: claude.ai → Code →
the environment chip next to the message box (e.g. "Default") → edit → Environment
variables, in `.env` format (`ODDS_API_KEY=xxxx`, no quotes). The key itself comes
from **the-odds-api.com** — free tier, 500 credits/month (the weekly job uses a
handful), emailed on signup. Environment variables load when a session container
starts, so a newly saved key is picked up by the next fresh container, not any
already-running session. `scripts/fetch_card_odds.py` is the consumer.

### Why is there no email delivery of predictions?

Two scars: SMTP is unreachable from the cloud environment, and a Gmail app password
was once leaked into git history wiring the old email path (revoked since —
revoke-and-avoid, don't reintroduce). Delivery is the push to
`weekly-predictions-log` plus a phone push notification.

### Is the ponytail skill used in this project?

Yes, at two levels: the skill itself is checked into the repo at
`.claude/skills/ponytail/` (so it travels with the code to any machine), and a
CLAUDE.md ground rule has coding tasks load it at full intensity first —
laziest working solution, reuse before writing new, shortest diff that works.
`ponytail:` comments in the notebook mark spots where that reasoning is
recorded (e.g. why calibration was removed in the Threshold Selection cell).

### Why are the raw CSVs committed to git?

ufcstats blocks datacenter IPs, so "re-scrape anytime" is false in most
environments — and committed data pins every experiment to the exact rows it
trained on. A data refresh is a new scrape committed together with the retrain it
feeds. (Gitignored before Aug 2026; this was the fix.)
