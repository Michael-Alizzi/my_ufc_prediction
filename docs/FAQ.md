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

### Are we sometimes betting against the market? (e.g. Gomes, Shanghai Aug 2026)

Yes — value bets come in two species. **Against the market's direction**:
model and market disagree on the winner (Gomes: market's 2.28 implies
~44%, model says 53.4% — the market picks Yan, the model narrowly picks
Gomes; the bet pays off if her true chance is anything above ~44%).
**With the market, more conviction**: both agree on the winner, the model
is just more confident than the price (Sumudaerji on the same card:
75.3% vs ~69% implied) — a disagreement of degree, not direction. The
honest caveat on the first kind: "model near a coin flip vs a one-sided
market" was historically the model's worst segment (−9.5% ROI for the old
odds-blind model). Two mitigations now: the current model ingests the
market price as a feature, so a residual disagreement is deliberate; and
when rule E's shrink-toward-market *still* finds value after conceding
half the opinion (it staked Gomes its maximum), the disagreement has
survived the humility check. It remains the bet type most worth watching
across the trial when it loses.

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

- **`ufc-weekly-card-day`, Friday 9 AM (`0 23 * * 4` UTC; Thursday 1 PM
  until 27 Aug 2026 — moved so odds are fetched closer to fight day while
  comfortably preceding every card's start, briefly Saturday 9 AM before
  Michael settled on Friday morning):**
  cheap ufcstats
  probe (usually blocked, skips gracefully) → WebSearch the next card → build/
  refresh `card.json` odds via `scripts/fetch_card_odds.py` (Sportsbet staking
  price + de-vigged AU-median feature price) → `send_weekly_predictions.py`
  (rule A's real $50 stakes + C/E/F shadow logs) → commit
  `predictions_output.md` + `card.json` to `weekly-predictions-log` → rebuild +
  republish the dashboard → phone notification with the slip.
- **`ufc-monday-scoring`, Monday 6 PM (`0 8 * * 1` UTC; Friday until 27 Aug
  2026 — moved to land the day after Sunday-AEST fights, and always BEFORE
  Friday's card-day job replaces `card.json` with the next card):** find the most
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
*officially scored* (`scripts/score_card.py`, run by the Monday Routine) —
not when the fights end. Between the event and its scoring run the
dashboard correctly shows the pre-event state. Scoring can be run early by
hand when results are in (UFC 330 was scored the Sunday it finished, at
Michael's request); the Monday run then finds nothing left to score.

### Why is a card scored a day or two after it happens?

Cards run Saturday night US time — Sunday afternoon AEST — and the scoring
Routine runs Monday 7:30 AM AEST, so each card is graded the morning after it
ends. (Until 27 Aug 2026 scoring ran Fridays, a ~6-day lag; it was moved with
the card-day swap both for speed and because scoring must land before the
card-day job replaces `card.json` with the next card. The Monday slot itself
moved from 6 PM to 7:30 AM on 13 Sep 2026.) Ask any time after an event to
score it earlier by hand; Monday's run then finds nothing left to do.

### Do fights ever happen on Saturday AEST — does the card-day run always beat them?

Yes they do, routinely. Asia-hosted cards (Shanghai, Macau, Tokyo) run
Saturday *local* evening = Saturday evening AEST, prelims from
~4&ndash;5 PM; US cards are Sunday AEST midday, Europe/Middle East
Sunday early morning, Australian cards Sunday midday. The data (771
events): 639 Saturday-listed; since 2023 only two exceptions, one
Friday (Aug 22 2025) and one Sunday (Jun 2026). That Friday one turned
out to be a **Shanghai card fighting Friday local time — Friday evening
AEST** (~5&ndash;11 PM), which a Saturday-morning run would have missed
outright; a Friday-*US* card (the other rare shape) fights Saturday
~9 AM&ndash;3 PM AEST. The card-day run was briefly Saturday 9 AM
(clears Asia Saturday cards, misses a Friday-Asia card, wire-tight on
Friday-US) before settling at **Friday 9 AM AEST** (28 Aug 2026), which
beats both rare Friday shapes and every normal one with hours-to-a-day
of margin. A true weekday card (25 Wednesdays all-time, 3 since 2020,
all COVID-era) would still be missed and needs a manual "run the card
job early" — essentially extinct.

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
week's exact slip lives in two places, both refreshed by Friday morning's
card-day Routine: the dashboard's **Performance tab → upcoming card** (with
the bankroll allocator and the total-if-all-win row), and
`predictions_output.md` on the `weekly-predictions-log` branch (the "Your
bet" column). Worked example — Hernandez vs. Rodrigues, Aug 22 2026: $11
Padilla @2.01, $18 de Ridder @1.25, $21 Hernandez @1.56; max loss $50,
~$77 back (+$27) if all three win.

### When should I actually place the stakes each week?

After the **Friday 9 AM AEST run's notification** — that's the slip built
on the freshest odds, and stakes shift when prices move (Padilla went
$9→$11 and Mederos dropped out entirely between two runs of the same
card once). The window is then Friday morning to the card's first prelim
— Saturday ~4–5 PM AEST for Asia cards, Sunday morning AEST for US ones.
If two slips ever exist for one card (an early manual run plus Friday's),
bet the Friday one; the ledger is always scored against the latest logged
slip, so betting the same one keeps your real money aligned with the
recorded trial.

### What's the Avg CLV column?

Closing-line value: did the price we took beat the price the market
closed at? Per bet, `taken_odds / closing_odds − 1` (positive = the line
moved toward our pick after we bet — the market "agreed" late); the
ledger logs each rule's per-event average. Mechanics: the Friday card-day
job schedules a one-off snapshot ~90 min before the card's first fight
(`scripts/snapshot_closing_odds.py` → `closing_odds.json` on the log
branch), and Monday's scoring computes CLV from it — the snapshot must
happen pre-fight because The Odds API drops events once they start. Why
it matters: CLV grades the *decision* (the price) rather than the
*outcome* (the coin flip), so it separates skill from luck in far fewer
bets than W/L — beating the close consistently is the standard early
indicator of real edge, which matters given the 10-event trial's limited
power. Worked example: take Gomes at 2.28 on Friday; if she closes 2.10
(late money agreed), CLV = 2.28/2.10 − 1 = +8.6% — evidence of skill
even if she then loses; if she drifts to 2.50, CLV = −8.8% — the
market's sharpest read moved against us, a warning even if she wins.
Like buying a stock at $10 that closes the day at $11: any one trade can
still lose, but consistently buying below where the market settles makes
profit a matter of time. It's a diagnostic only: no staking rule uses
it, and the promotion criterion is unchanged.

### Where do I see how the bets are going?

The **Octagon Ledger dashboard**:
<https://claude.ai/code/artifact/5d7c8637-557d-4ec2-981c-9255b986f52f> — a
Performance tab (money view: P/L so far, rule-A chart, bankroll allocator,
past-events detail) and an Experiments tab (rule comparison, chart, and
backtest reference) with these docs as the other tabs. It is generated by
`scripts/build_dashboard.py` from `ledger.md`; the Monday scoring Routine
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

### Are the scoring / card-day Routines turned off?

No. Both are `enabled: true` in the Routines API, with live schedules and
recent successful fires (schedules shown as of the 27 Aug 2026 swap —
card day moved Thursday→Saturday, scoring Friday→Monday and renamed
`ufc-monday-scoring`):

| Routine | Cron (UTC) | Local time |
|---|---|---|
| `ufc-weekly-card-day` | `0 23 * * 4` | Fri 9 AM AEST |
| `ufc-monday-scoring` | `30 21 * * 0` | Mon 7:30 AM AEST |

Neither carries an `ended_reason` (permanently disabled) or a
`suspension_reason` (temporary hold, e.g. a paused subscription) — the two
fields that would explain a genuinely dead Routine. Greyed-out styling in
the Routines list is not the off state; the enable toggle is.

One thing that *does* make these two look different from a normal Routine:
they are **self-bound** — they fire into the existing UFC session
(`persistent_session_id`) rather than spawning a fresh session each time, so
they report no per-run `last_run` record in the list (only `last_fired_at`).
That's by design: each week's job continues the same conversation. If they
ever do stop, the tell is `last_fired_at` going stale relative to
`next_run_at`, not the row's shading.

### If our fighter's odds shorten after we bet, is that positive CLV? What about the opponent drifting?

Yes on both — they're the same event seen from opposite corners. Taking
Gomes at 2.28 and watching her close at 2.00 gives CLV = 2.28/2.00 − 1 =
**+14%**: the market moved toward our position after we took the price,
which is the standard leading indicator that the model is finding real
value (it says the final, sharpest consensus agreed with us — a faster and
less noisy signal than whether she then wins the coin flip).

The opponent case is the mirror image. We never bet "against" a fighter
directly — we bet **on** the other corner — and the ledger's Avg CLV is
always computed on the side we took (our taken odds vs *that fighter's*
closing odds; `score_card.py:avg_clv`). But a two-outcome market's prices
move together: an opponent drifting 2.00 → 3.00 (implied 50% → 33%) forces
our pick to shorten by roughly the same probability mass, e.g. 2.00 →
~1.50, which grades as 2.00/1.50 − 1 = **+33%** CLV on our side. So
"opponent drifts out" and "our fighter steams in" are one movement, and
both show up as positive CLV on the bet we logged.

Two caveats worth keeping in mind: (1) direction matters — our pick's odds
going *down* is good for CLV (we locked a bigger payout than the close
offers), which feels backwards until you remember we already hold the
2.28 ticket; and (2) one fight's CLV proves nothing by itself — lines move
on injury news and betting volume too. It's the *average* staying positive
across many bets that indicates edge, which is exactly why it's logged
per event and averaged in the dashboard's Rule comparison table.

### Could we do something with CLV beyond watching it as an indicator?

Four real uses, in rough order of practicality:

1. **Bet timing.** We bet Friday morning only because that's when the job
   runs. Avg CLV directly measures whether Friday prices beat fight-day
   prices on our bets — a few months of ledger data answers "should the
   card-day job move earlier or later?" with evidence, no code needed.
2. **A real-money circuit breaker.** CLV converges much faster than W/L,
   so a clearly negative average after ~15–20 bets is strong evidence the
   model pays worse-than-market prices — grounds to stop staking real
   dollars and keep shadow-logging, before the bankroll ledger has enough
   events to show it.
3. **Post-trial tie-breaker between staking rules.** If the entry-9
   Wilcoxon trial ends in a statistical tie (likely, per the power
   analysis), prefer the rule whose bet selection got the best prices.
   Mid-trial it stays hands-off — the promotion criterion is
   pre-registered and frozen.
4. **Sharper phase-2 training data.** `collected_odds.csv` stores Friday
   prices; closing prices are strictly better probability estimates and
   we now capture them anyway. Routing snapshot closes into the training
   feed is a small PR-sized change; the raw data accrues regardless since
   `closing_odds.json` is committed per event.

Not on the menu: changing staking mid-trial, or reacting to any single
fight's CLV — one line move is noise; only the average means anything.
Current plan: let snapshots accrue, revisit the circuit breaker at ~15
covered bets, queue the training-feed change for phase-2.

### Can we work out CLV for events that already happened?

Retroactively, yes — approximately. Our own snapshot can't run backwards
(The Odds API drops events at commence time and paywalls history), but
closing lines for past fights are public record on Best Fight Odds, so
the three scored trial events were graded by hand against a median of 5
US sportsbooks' closes (exchanges excluded — Polymarket/Kalshi trade
in-play, so their "close" already knows the result):

| Rule | Avg CLV (3 events) |
|---|---|
| A | +2.5% |
| C | +5.3% |
| E | +5.3% |
| F | +2.6% |

Pooled over all 9 bets: +2.5%, with 7 of 9 at or ahead of the close.
Standouts: Padilla +11.3% and Donte Johnson +9.5% (big steam toward us),
Magny −13.2% (market drifted hard against us — and he won anyway, while
+7.8%-CLV Alvarez lost: the clean illustration that CLV grades the price,
not the coin flip). C/E lead because they skipped the Magny bet on
UFC 330.

Two caveats: our taken prices are Sportsbet (AU) and these closes are a
US-book median, so cross-book noise of a point or two applies — the live
pipeline (Sep 2026 onward) is same-book at both ends and cleaner. And
these retro numbers deliberately stay OUT of the ledger: the official
Avg CLV column only ever contains same-book snapshot values, so its
average isn't a mix of two measurement bases.

### Does the dashboard show who and how much the shadow rules bet at each event?

Yes — since Sep 2026, under **Experiments → "Bets by event · every rule"**:
one collapsible entry per scored event, each fight shown with its bet-on
fighter, odds, and a stake column per rule (A staked, C/E/F shadows),
rebuilt from the same shadow strings `score_card.py` grades from. The
summary row shows every rule's net for the event side by side. It
originally landed as an extra column in Performance → Past events, then
moved to Experiments the same day since that tab owns the shadow trial —
Past events stays Rule-A-only (the real money view). Most weeks all four
rules pick the same fighters and differ only in sizing; the interesting
rows are where a rule sits a fight out (like C/E skipping three of Rule
A's four UFC 330 bets).

### Why did the allocator show fights the model wasn't betting (e.g. Ruziboev vs Page)?

The Performance tab's bankroll allocator used to render every fight the
model could predict, including ones where it found no value — those rows
sat at a permanent $0 stake whatever bankroll you typed (the splitting
maths always ignored them; only the display included them). Fixed Sep
2026: the table now lists only the fights with a positive Kelly edge,
and the "N of M fights the model finds value in" line above it carries
the rest of the context. The model's full read on a card (picks with no
value attached) still lives in predictions_output.md on the
weekly-predictions-log branch.

### Why isn't the latest event in the dashboard as past data yet? Doesn't that happen Monday mornings?

It does now — the scoring Routine fires Monday 7:30 AM AEST (cron
`30 21 * * 0` UTC, i.e. Sunday 21:30 UTC). Until 13 Sep 2026 it ran Monday 6 PM, so a card
fought Sunday morning AEST sat as the "upcoming card" in the Performance
tab's allocator for most of Monday. Either way the run does the same work:
fetch results, `score_card.py` (with the pre-fight CLV snapshot since Sep
2026), append ledger.md and winners.json, republish the dashboard. The
morning slot still clears late-finishing Sunday-AEST cards (a US Saturday
card ends around 8 PM Sunday AEST at the latest) and lands days before
Friday's card-day job replaces card.json. On-demand scoring is always
available by asking in the session — the Routine is a floor, not a gate.

### Can the scoring Routine run Monday morning instead of the evening?

Yes — done 13 Sep 2026. `ufc-monday-scoring` now fires at **Monday 7:30 AM
AEST**, stored as cron `30 21 * * 0` (7:30 AM AEST = 21:30 UTC the previous
day, so the cron's day-of-week is Sunday even though the job is a Monday
job).
Nothing else about the job changed: same bankroll, same rules A/C/E/F
grading, same dashboard republish. The timing constraints it has to respect
are unchanged and both still hold — it must land *after* the last fight of a
Sunday-AEST card (a US Saturday main event finishes ~2 PM AEST Sunday,
Asia cards earlier) and *before* Friday's card-day job overwrites
`card.json` with the next event.

### Where is this project tracked outside the repo?

Jira, as **[KAN-8 "UFC Prediction"](https://cinder.atlassian.net/browse/KAN-8)**
— a Story under the *Business* epic (KAN-2) in Michael's Space. Connected to the
repo's own records on 13 Sep 2026: the ticket description now carries the links
(repo, Octagon Ledger dashboard, `ledger.md` on the log branch, EXPERIMENTS.md and
the docs) plus a dated status block, and seven subtasks split the work:

| Subtask | What it tracks | Status |
|---|---|---|
| [KAN-52](https://cinder.atlassian.net/browse/KAN-52) | Model experiment log, entries 1–10 | Done |
| [KAN-53](https://cinder.atlassian.net/browse/KAN-53) | Automatic results logging into `ledger.md` | Done |
| [KAN-54](https://cinder.atlassian.net/browse/KAN-54) | 10-event staking trial, A live + C/E/F shadow | In Progress (4/10) |
| [KAN-55](https://cinder.atlassian.net/browse/KAN-55) | Friday card-day + Monday scoring Routines | Done |
| [KAN-56](https://cinder.atlassian.net/browse/KAN-56) | Octagon Ledger dashboard | In Progress |
| [KAN-57](https://cinder.atlassian.net/browse/KAN-57) | Reliability curve + Brier reporting | To Do |
| [KAN-58](https://cinder.atlassian.net/browse/KAN-58) | Monthly research Routine + next experiment queue | In Progress |

Jira is the outside-in view (what's open, what's done); `EXPERIMENTS.md` and
`ledger.md` remain the actual records, and nothing syncs automatically — the
ticket is updated by hand when a stream's state changes, e.g. when the trial's
tenth event is graded.

### What is KAN-57 (calibration reporting) actually asking for?

[KAN-57](https://cinder.atlassian.net/browse/KAN-57) is the unfinished half of
the second "worth adding" item on the Jira story: *a Brier score or reliability
curve alongside precision, since calibration is what actually matters and
precision won't reveal a miscalibrated model.*

**What already exists.** More than the ticket's one-liner suggests:

1. A **Platt calibrator** is fitted every run (notebook § Probability
   Calibration) — a slope-only logistic regression on pooled walk-forward OOF
   scores centred at 0.5, `σ(β·(p − 0.5))`, currently β ≈ 4.6. Slope-only, so
   raw 0.5 maps to calibrated 0.5 exactly and the displayed favourite can never
   contradict the 0.5 decision.
2. A **Brier non-regression assert** guards it: `calibrated_brier <= raw_brier +
   0.01`.
3. Every experiment entry reports **model log-loss vs the market's vig-free
   log-loss** on the pooled-OOF fights matched to closing odds.

**What is missing** is anything that looks at calibration *by probability band*.
Log-loss and Brier are single numbers over ~7.9k fights; they can look fine while
particular bands are badly off, and the McNemar/Wilcoxon gates only test picks
and ROI. Binning the shipped artifact's own OOF pool takes about ten lines and
shows it immediately:

| raw p(red) bin | n | mean predicted | actual red win rate | gap |
|---|---|---|---|---|
| 0.1–0.2 | 241 | 0.160 | 0.266 | −0.106 |
| 0.2–0.3 | 482 | 0.252 | 0.409 | −0.157 |
| 0.3–0.4 | 654 | 0.357 | 0.466 | −0.109 |
| 0.4–0.5 | 1684 | 0.456 | 0.520 | −0.064 |
| 0.5–0.6 | 1702 | 0.544 | 0.635 | −0.091 |
| 0.6–0.7 | 996 | 0.648 | 0.710 | −0.061 |
| 0.7–0.8 | 958 | 0.752 | 0.808 | −0.056 |
| 0.8–0.9 | 772 | 0.844 | 0.880 | −0.036 |

The gap is **negative in every bin**: red outperforms its prediction whether the
model favours red or blue. That is not under-confidence (which would flip sign
either side of 0.5) — it is a **base-rate shift**. Across the pool the model
predicts red at 55.8% while red actually wins 63.3%, because `mirror_fights()`
trains on an exactly 50/50 prior while the OOF rows are real, corner-ordered
fights where ufcstats lists the favourite as red more often than not.

**The trap this reveals.** Refitting the calibrator *with* an intercept removes
most of the gap and looks spectacular — pooled-OOF log-loss 0.6009 → 0.5886,
Brier 0.2083 → 0.2027. That 0.012 of log-loss is roughly the size of the entire
market gap this project exists to close. It is **not skill**: it is the
red-corner prior, and it maps raw 0.5 to 0.594, breaking the rule that the
displayed favourite matches the decision. Any future calibration work must
report the shift and the symmetric (under/over-confidence) components
separately, or it will bank a corner artifact as an edge.

**Two related findings the binning turned up**, both folded into KAN-57:

* The slope-only calibrator currently makes the pooled OOF *slightly worse* on
  the very pool it was fit on — Brier 0.2083 → 0.2087, log-loss 0.6009 → 0.6029.
  Not a regularisation artifact (an unpenalised refit gives β = 4.705 and the
  same numbers); the no-intercept family simply cannot beat the raw score here.
  It passes only because the assert allows +0.01 of Brier slack. So the
  calibrator may be earning nothing and could be dropped — worth deciding
  explicitly rather than leaving it in because it "doesn't hurt".
* **The backtest and the live job use different probabilities.** `oof_export`
  stores the *raw* stacked score, so `odds_backtest.py`, `betting_rule_compare.py`
  and the dashboard's History replay all bet off raw probabilities — including
  the λ fit behind rule F. Live, `predict_winner()` returns the *calibrated*
  probability and `send_weekly_predictions.py` feeds that straight into
  `kelly_edge`. Mean |calibrated − raw| is only 0.012 (max 0.083), but residual
  edges are small by construction (entry 9), so that is enough to flip marginal
  bets on or off. Backtested ROI and live staking should run off the same number.

**Scope, then.** Add a reliability curve, a per-decile calibration table and a
Brier score to the notebook's stability-check cell, computed on pooled OOF and
split into shift vs symmetric components, with the market's own curve on the
same axes; then decide from the evidence whether the calibrator stays, and make
the backtest and the weekly job agree on raw-vs-calibrated. Reporting plus one
consistency fix — no threshold change, and the 0.5 decision rule and §11's
no-tuning scar stand.

### Why calibrate so the scores average to 0.5?

They don't average 0.5 — and that's the useful part of the question. On the
shipped artifact's OOF pool the calibrated scores average **0.5566**, against a
red win rate of 0.6327. The constraint isn't on the mean, it's on a single
**point**: `fit_intercept=False` on the score centred at 0.5 pins raw 0.5 to
calibrated 0.5. Everything else is free to move.

Three reasons that anchor is there.

**1. A fight has no red corner at predict time.** `predict_winner(red, blue)`
takes red = `fighter1` from `card.json`, which `scripts/fetch_card_odds.py`
fills from the odds API's `home_team`/`away_team` — an arbitrary label in MMA,
not a corner. So the model must give the same answer whichever way the pair is
passed: p(A beats B) + p(B beats A) = 1. The slope-only map delivers that
exactly, because σ is antisymmetric — σ(−x) = 1 − σ(x) — so
`f(1 − p) = 1 − f(p)` identically:

| raw p | shipped `f(p) + f(1−p)` | with an intercept |
|---|---|---|
| 0.30 | 1.000000 | 1.157 |
| 0.45 | 1.000000 | 1.185 |
| 0.60 | 1.000000 | 1.179 |
| 0.80 | 1.000000 | 1.128 |

With an intercept the model contradicts itself on argument order: raw 0.5 maps
to 0.594, so pass the same even matchup both ways and *both* fighters come back
"favoured at 59.4%".

**2. The decision would drift away from the display.** The winner is decided on
the raw score at 0.5. An unconstrained intercept was tried first and mapped 0.5
to 0.61 — every fight with raw in [0.41, 0.50) was decided one way and displayed
favouring the other. That is a real shipped bug, which is why the notebook cell
carries the comment it does.

**3. The intercept would be learning the corner, not the fighters.** What it
picks up is the red-corner base rate — ufcstats lists the favourite as red more
often, so red wins 63.3% of OOF rows while a mirror-trained model predicts 55.8%.
Real in that dataset, worthless live, where red is whoever the odds feed listed
first. Applying it would inflate whichever fighter appears first on the card, and
Kelly would stake on the inflation.

**The cost, stated honestly.** A slope can only expand or shrink probabilities
symmetrically about 0.5; it cannot shift them. So the per-band gaps in the
KAN-57 entry above don't get corrected — they persist by design. The right
reading is that they are the price of order-invariance, not a defect: 0.5 is
also exactly where `mirror_fights()` puts the training prior, so the anchor and
the training design agree on what "no opinion" means.

### What does "centred at 0.5" mean?

A subtraction. The calibrator isn't fitted on the probability `p`, it's fitted
on `x = p − 0.5`:

```python
calibrator.fit((oof_proba.values - 0.5).reshape(-1, 1), oof_y.values)
```

So a raw score of 0.5 becomes x = 0, 0.8 becomes x = +0.3, 0.2 becomes x = −0.3.
"Centred at 0.5" just means the input is re-expressed as *distance from 0.5*
rather than as a probability. `predict.py` does the same shift at serving time —
`predict_proba([[raw_proba - 0.5]])`.

Why it matters is what it combines with. A logistic regression outputs
σ(β·x + c), and `fit_intercept=False` forces c = 0. At x = 0 that gives
σ(0) = 0.5 **exactly, whatever β turns out to be**. So:

* centring chooses *which* raw score is the fixed point (0.5, the neutral score);
* dropping the intercept is what actually pins it.

Neither does the job alone. With the shipped β ≈ 4.615:

| raw p | x = p − 0.5 | σ(β·x) |
|---|---|---|
| 0.20 | −0.30 | 0.2003 |
| 0.35 | −0.15 | 0.3335 |
| 0.50 | 0.00 | **0.5000** |
| 0.65 | +0.15 | 0.6665 |
| 0.80 | +0.30 | 0.7997 |
| 0.95 | +0.45 | 0.8886 |

Fit the same no-intercept model on `p` *without* centring and it anchors the
wrong point — β comes out 1.32, and now p = 0 maps to 0.5 while p = 0.5 maps to
0.659. A fight the model calls a certain loss for red would display as a coin
flip. Centring is what moves the anchor from p = 0 to p = 0.5.

(Aside visible in that table: σ(4x) ≈ 0.5 + x for small x, so β ≈ 4.6 is close to
the identity map — which is why the calibrator moves scores by only 0.012 on
average, and why KAN-57 asks whether it is earning its place at all.)

### Same thing, explained simply

Think of the model's output as a tug-of-war rope with a marker in the middle.

The model gives every fight a number between 0 and 1 — how confident it is that
the red-corner fighter wins. **0.5 is the middle of the rope: no opinion, a coin
flip.** 0.8 means red is pulling hard. 0.2 means blue is.

**Calibration** is a dial we turn afterwards. Trained models are often bad at
saying *how* sure they are — a model can be right about who wins but say "70%"
for fights that actually happen 80% of the time. The dial stretches or squeezes
those numbers so that fights shown at 70% really do win about 70% of the time.
It never changes *who* is favoured, only by *how much*. We set the dial using
thousands of past predictions, so it's fixing a real pattern, not one week's
noise.

**"Centred at 0.5"** means that before the number goes into the dial, we
subtract 0.5 from it — so instead of feeding in "0.8", we feed in "+0.3, i.e.
three-tenths of the way toward red". Like measuring temperature from freezing
instead of from absolute zero: same information, but now zero means something
useful.

Why bother? Because of how the dial is built: **whatever you feed in as zero
comes back out as 50/50.** Subtracting 0.5 first is what makes 0.5 the thing
that maps to zero — so a fight the model genuinely can't call goes in at the
middle of the rope and comes out at the middle of the rope. The marker stays put
no matter how hard we turn the dial.

Skip the subtraction and the dial anchors the wrong end of the rope: a raw score
of 0 — the model is *certain* red loses — would come back as 0.5, a coin flip,
and a true 50/50 fight would come back as 66% for red. Both nonsense, and since
we bet real money off these numbers, expensive nonsense.

So: the dial adjusts how strongly we read the pull; centring at 0.5 is what
guarantees the middle of the rope is still the middle afterwards.

### Worked example: the calibration maths, number by number

One fight. The model says **0.72** for the red-corner fighter. Here is every
step, with the shipped dial setting β = 4.6149.

**Step 1 — centre it.** Subtract the neutral point:

```
x = p − 0.5 = 0.72 − 0.5 = 0.22
```

`p = 0.72` is the model's raw confidence red wins. `0.5` is the coin-flip point.
`x = 0.22` is how far toward red the model is leaning — *signed*, so positive
means red, negative means blue. This is the only thing the dial ever sees.

**Step 2 — turn the dial.** Multiply by β:

```
z = β × x = 4.6149 × 0.22 = 1.0153
```

`β = 4.6149` is the **only number the calibrator learns** — one slope, fitted on
~7,900 past predictions so that the numbers it produces match how often those
fights actually went that way. It says how much a unit of "leaning" is worth.
Because of the shape of the curve, **β = 4 is roughly the do-nothing setting**;
above 4 stretches confidence away from the middle, below 4 squeezes it toward
the middle. Same raw 0.72 under different dials:

| β | 0.72 becomes | meaning |
|---|---|---|
| 2 | 0.608 | heavy squeeze — "you're overconfident" |
| 4 | 0.707 | leave it about as it was |
| **4.6149** | **0.734** | the fitted value: a mild stretch |
| 8 | 0.853 | heavy stretch — "you're underconfident" |

**Step 3 — turn it back into a probability.**

```
calibrated = 1 / (1 + e^−z) = 1 / (1 + e^−1.0153) = 0.7340
```

`z = 1.0153` is in **log-odds**, the natural scale for this curve. Un-log it and
it's plain betting odds: e^1.0153 = **2.76**, i.e. red wins 2.76 times for every
1 loss. As a probability that's 2.76 / (2.76 + 1) = **0.734** — the same answer.
z = 0 would be 1-to-1, a coin flip, which is exactly the anchor the centring in
step 1 bought us.

So **0.72 → 0.734**: a stretch of +0.014.

**The mirror check.** Pass the same fight the other way round (blue listed
first) and the raw score is 0.28, so x = −0.22, z = −1.0153, calibrated =
**0.266**. And 0.734 + 0.266 = 1.000000 exactly. The model can't contradict
itself on argument order — see the anchor entry above for why that matters.

**What it's worth in money.** Say a bookmaker offers 1.50 on red.

| | probability | fair price | edge at 1.50 | Kelly fraction |
|---|---|---|---|---|
| raw | 0.7200 | 1.389 | +0.0800 | 16.0% |
| calibrated | 0.7340 | 1.362 | +0.1011 | 20.2% |

Edge is `p × odds − 1`; the Kelly fraction is `edge / (odds − 1)` — that's
`kelly_edge()` in `predict.py`, and the weekly job splits the bankroll across
value bets in proportion to it. A **1.4-percentage-point** change in the
probability becomes a **26% bigger stake**. That is the whole reason KAN-57 cares
that the backtest bets off raw scores while the live job stakes off calibrated
ones: on small edges, a difference this size decides both how much goes on and
whether the bet is placed at all.

### I've done Platt scaling before to make the average score match the average rate — we never centred. Why here?

Because you had an intercept, and that changes everything about whether centring
matters.

**With an intercept, centring is a no-op.** Standard Platt is σ(a·s + b). Feed it
the centred score instead and you get σ(a(s − 0.5) + b′), which is the same
function with b′ = b + 0.5a — same family, same fit, same predictions. Checked on
this project's OOF pool: fitted uncentred gives a = 4.3221, b = −1.7828; fitted
centred gives a = 4.3169, b = 0.3788, and −1.7828 + 0.5(4.3221) = 0.3783. The
predictions differ by 4×10⁻⁴, which is just solver tolerance. So not centring was
the right call — it would have bought you nothing.

**And the mean-matching you relied on came free.** You didn't have to engineer it:
maximum-likelihood logistic regression with an intercept has the first-order
condition Σ(yᵢ − p̂ᵢ) = 0, which *is* "mean predicted = mean actual" on the fit
data. On this pool the intercept-ful fit gives mean predicted 0.632724 against a
base rate of 0.632736. The intercept is the parameter that does it; drop it and
the guarantee goes with it.

**Which is exactly what we do here, on purpose.** Our calibrator has no
intercept, so its mean comes out 0.5566 against a 0.6327 base rate — off by 7.6
points. In your sales model that would be a straightforward bug: the population
really does convert at some rate, so a model whose average misses it will
overstate expected revenue.

Here the "base rate" is not a property of the world. Red wins 63% of rows because
ufcstats tends to list the favourite in the red corner — a labelling convention.
Live, red is whoever the odds feed happened to name first, so there is no rate to
match. Meanwhile the thing we *do* need is that p(A beats B) + p(B beats A) = 1,
and only the no-intercept form gives that. Base-rate matching and order-invariance
are in direct conflict for this problem, and order-invariance wins.

**The reconciliation, and a concrete job for KAN-57.** The two goals stop fighting
if calibration is measured on a **mirrored** OOF pool — every fight included in
both orientations. Then the base rate is exactly 0.5 by construction, the
corner convention cancels out, and mean-matching and antisymmetry agree. Any
miscalibration still visible there is real (genuine over- or under-confidence),
not a labelling artifact. It needs a small change to the export cell, which
currently stores one orientation per fight (7,869 rows, no duplicates) — the
swapped-corner predictions aren't saved, so they can't be recovered after the
fact.

### In the mirror check, what is 0.266, and what's red's equivalent?

The thing to hold onto: **the model never knows anyone's name.** It always answers
one question — *what is the probability that the fighter I was handed first
wins?* Swap who you hand it first and it answers a different question about the
same fight.

| | run 1: red handed first | run 2: blue handed first |
|---|---|---|
| raw p (first fighter wins) | 0.72 | 0.28 |
| x = p − 0.5 | **+0.22** | **−0.22** |
| z = β·x | **+1.0153** | **−1.0153** |
| e^z, as odds | 2.76 wins per loss | 0.362 wins per loss (≈ 1 win per 2.76 losses) |
| calibrated answer | **0.7340** | **0.2660** |
| in words | "red wins 73.4%" | "blue wins 26.6%" |

So 0.266 is **blue's win probability**, and red's equivalent is **0.734** — the
number from run 1. They aren't two different beliefs, they're the same belief
written from two viewpoints. Notice the sign of x and z simply flips: a positive
z means the first-listed fighter is favoured, a negative z means they're the
underdog.

**Why the sum matters.** Exactly one fighter wins, so the two answers have to add
to 1. Ours give 0.734 + 0.266 = 1.000000. If they summed to, say, 1.05, the model
would be claiming a 105% chance that somebody wins the fight — and you could back
*both* fighters and show a profit on paper that doesn't exist.

**Where this actually bites.** The weekly job never runs the model twice. It runs
it once and gets the other side by subtraction:

```python
for name, p, o in ((fight["fighter1"], proba, fight.get("odds1")),
                   (fight["fighter2"], 1 - proba, fight.get("odds2"))):
```

That `1 - proba` is only honest if the model really would have said 0.266 when
handed blue first. The mirror check is what proves the shortcut is legitimate.
With an intercept in the calibrator it wouldn't be: the model would have said
something else, and every blue-side stake on every card would be sized off a
number the model never actually produced.

### What is each fighter worth in dollars?

Two different dollar questions, and they have different answers.

**1. The fair price — what each side is worth as a price.** Flip the probability:

| | probability | fair decimal price | $10 at that price returns |
|---|---|---|---|
| red | 0.7340 | 1/0.7340 = **1.362** | $13.62 |
| blue | 0.2660 | 1/0.2660 = **3.759** | $37.59 |

These are the prices at which *neither* bet makes or loses money in the long run
— the model's own vig-free book. The two implied probabilities add to exactly
1.0000, which is the mirror check from the entry above showing up as money: a
real bookmaker's two prices always add to *more* than 1, and the excess is the
vig.

**2. What actually goes on the fight.** That needs a bookmaker's price to compare
against. Say the book offers red 1.50 and blue 2.50 (6.7% overround):

| | model p | offered | implied | edge = p×odds − 1 | Kelly |
|---|---|---|---|---|---|
| red | 0.7340 | 1.50 | 0.6667 | **+0.1010** | 0.2020 |
| blue | 0.2660 | 2.50 | 0.4000 | −0.3350 | 0 |

Red is worth backing at 1.50 because the book prices it at 66.7% and the model
says 73.4%. **Blue is worth $0** — at 2.50 the book is asking for 40% and the
model only gives it 26.6%. At most one side of a fight can ever be a value bet.

**The stake is not the Kelly fraction.** That 0.2020 is a *weight*, not "20% of
the bankroll". Rule A deploys the whole $50 across a card's value bets in
proportion to their Kelly numbers:

* if red is the card's only value bet, the **entire $50** goes on it — returning
  $75 (profit +$25) if red wins, −$50 if not;
* if the card has one other value bet with Kelly 0.05, the split is 0.2020 :
  0.05, so **$40 on red and $10 on the other**.

**What would make blue backable?** Blue needs a price above its fair 3.759. At
3.50 the edge is still −0.069. At 4.00 it turns +0.064, a Kelly of 0.021 — a
real bet, but a tenth of red's weight, so on a card with both it would draw
about a tenth of the money.

### So β corrects under/over-confidence, centred at 0.5 because the model is biased toward red?

First half right, second half backwards — and the flip is the whole point.

**β does correct confidence.** That's exactly its job: β > 4 stretches scores away
from the middle (fixing under-confidence), β < 4 squeezes them toward it (fixing
over-confidence). One knob, one job.

**But the centring is not there to correct a red bias. It's there so that the
correction can never express one.** Think of two separate ways a model can be
miscalibrated:

* **Spread** — how far from the middle it dares to go. Symmetric: it treats both
  fighters the same. This is β's department.
* **Tilt** — systematically favouring one side regardless of who's fighting. This
  would need a *second* parameter, the intercept, which we deliberately don't
  have.

Centring at 0.5 plus `fit_intercept=False` removes the tilt knob from the model
entirely. A pure stretch about 0.5 pushes each score further out *in whichever
direction it already pointed* — it can never add a net lean toward red.

**And the red tilt in the data is real; we just refuse to correct it.** Red wins
63.3% of the historical rows while the model averages 55.8%. That gap is left
sitting there on purpose, because "red" is a listing convention (ufcstats tends
to put the favourite there), not a property of a fighter — and live, red is
whoever the odds feed happened to name first. Correcting it would mean
systematically inflating whoever appears first on the card.

The numbers show β is powerless against it anyway: calibration moves the mean
prediction from 0.5580 to 0.5566 — **fourteen ten-thousandths**, against a gap of
7.5 points. Only an intercept could close that, which is the fix we don't want.

So: **β = how confident, and nothing else. The centring = a guarantee that the
correction stays even-handed between the two corners.**

### So β corrects under/over-confidence, and centring stops a red bias?

First half exactly right, second half worth straightening out — they're two
separate knobs doing two separate jobs.

A logistic calibrator σ(a·x + b) has only two things it can do:

* **the slope `a` (our β) — how confident.** Stretches or squeezes the
  probabilities symmetrically about the anchor. β > 4 stretches (fixes an
  under-confident model), β < 4 squeezes (fixes an over-confident one). This is
  the knob we keep and fit.
* **the intercept `b` — which way it leans.** Shifts everything one direction.
  This is the knob that would introduce a red bias, and we set it to zero.

So it isn't centring that prevents the red bias — **`fit_intercept=False` is**.
Keep the intercept and centre anyway and you still get the bias: fitted on this
project's pool it maps a raw 0.5 to 0.594, red-favouring, centred or not.

Centring does something different: it decides **which raw score the anchor sits
on**. With no intercept the map always pins whatever you feed in as zero, so
subtracting 0.5 first is what puts the pin on the neutral score. Skip it and you
still have no bias term, but the pin lands on p = 0 — a fight the model is
*certain* red loses would come back as a coin flip. Both pieces are needed, and
neither substitutes for the other.

One more correction worth making: the bias wouldn't be coming *from the model*.
The model is mirror-trained, so it has no corner preference to fix — it's the
calibrator's intercept that would go looking at the training labels, notice red
wins 63% of them, and bake that in. The anchor isn't repairing a biased model,
it's stopping the calibrator from adding a bias that was never there.

And note β couldn't fix a corner bias even if you asked it to: a slope moves both
sides equally in opposite directions, so it can never shift the level. Confidence
and lean are genuinely independent — which is why you can fit one and forbid the
other.

### Why 0.5 specifically?

It isn't really a choice — three independent requirements all land on it.

**1. The symmetry forces it.** We need p(A beats B) + p(B beats A) = 1, i.e.
f(1 − p) = 1 − f(p) for the calibration map f. Now set p = 0.5, the fight where
swapping the corners changes nothing:

```
f(0.5) = 1 − f(0.5)   ⟹   2·f(0.5) = 1   ⟹   f(0.5) = 0.5
```

Any map that treats the two fighters even-handedly *must* pin 0.5. There was
never a second candidate; picking a different anchor means giving up
order-invariance.

**2. It's what the training data says "no information" is.** `mirror_fights()`
adds every fight a second time with the corners swapped and the label flipped, so
the training set is exactly 50/50 by construction. A model fitted on that has a
prior of precisely 0.5 — so 0.5 isn't a convention, it's the score that means
"the features told me nothing about this fight".

**3. It's already the decision boundary.** The winner is picked by
`raw >= best_th` with `best_th = 0.5`. If the anchor sat anywhere else, the
display and the decision would disagree for every score between the two — the
exact bug that got shipped once when an unconstrained intercept moved the
crossing point to 0.61.

**What goes wrong anywhere else.** Take a fight the model genuinely can't call,
priced fair by the book at 2.00 each way, and move the anchor:

| anchor | coin-flip fight displays as | edge at 2.00 | what rule A does |
|---|---|---|---|
| 0.500 | 0.500 / 0.500 | +0.000 | no bet |
| 0.520 | 0.520 / 0.480 | +0.040 | backs the first-listed fighter |
| 0.550 | 0.550 / 0.450 | +0.100 | backs the first-listed fighter |
| 0.594 | 0.594 / 0.406 | +0.188 | backs the first-listed fighter, Kelly 0.188 |

Every non-0.5 anchor manufactures an edge on a fight we have no opinion about,
always on whoever happens to be listed first, and Kelly stakes real money on it.
(0.594 isn't hypothetical — it's what an intercept-ful fit on this project's pool
actually produces.)

That three separate arguments — symmetry, the training prior, and the decision
rule — pick the same number is why the design is stable. Move the anchor and all
three break at once.

### "The displayed favourite can never contradict the 0.5 decision" — how would it?

Every fight produces **two** numbers, from different places:

* the **decision** — who we say wins — comes from the **raw** score:
  `winner = red if raw_proba >= best_th else blue`, with `best_th = 0.5`;
* the **displayed confidence** comes from the **calibrated** score, then
  `confidence = proba if winner == fighter1 else 1 - proba`.

They describe the same fight, so they had better agree about who is favoured.

**Why the decision is made on the raw score at all.** Calibration is monotonic —
it stretches and squeezes but never reorders — so it cannot change which fighter
looks stronger. The *only* thing it could change is which side of 0.5 a score
lands on, and that is fixed entirely by where the map crosses 0.5. Pin the
crossing at 0.5 and thresholding the raw score and thresholding the calibrated
score are the *same decision*, always. The anchor turns "which number do we
threshold?" into a non-question.

**Unpin it and they come apart.** Fit the calibrator with an intercept on this
project's pool and you get σ(4.3221·p − 1.7828), which crosses 0.5 at a raw score
of **0.4125**, not 0.5. So every raw score in [0.4125, 0.5) is decided *blue*
while the calibrated number says *red* is favoured. Take raw = 0.45:

| | calibrated p(red) | printed row |
|---|---|---|
| shipped (slope only) | 0.4426 | prediction **BLUE**, confidence **55.7%** ✓ |
| with an intercept | 0.5405 | prediction **BLUE**, confidence **46.0%** ✗ |

That second row is nonsense on its face: we are picking blue and reporting 46%
confidence in blue. The weekly predictions table would print it exactly like
that, because `1 - proba` on a red-favouring calibrated number is below half.

**It isn't a rare corner case.** 1,557 of the 7,869 fights in the current OOF
pool sit in that band — **one fight in five**. On a typical 12-fight card that's
two or three rows where the pick and the confidence point at different fighters.

So the phrase means: because σ(β·(p − 0.5)) is pinned at 0.5, the calibrated
number is on the same side of even as the raw number for *every possible input*.
Not usually. Always.

### Isn't the 0.5 acting as the intercept?

A constant term does appear — but it isn't free, and that's the whole difference.

Multiply our model out:

```
σ(β·(p − 0.5))  =  σ(β·p − 0.5β)  =  σ(4.6149·p − 2.3074)
```

(identical to 2×10⁻¹⁶, i.e. exactly). So yes, there is a −2.3074 sitting there
looking like an intercept. The catch: it is **forced to equal −β/2**. Change the
slope and it moves with it. A real intercept is a number the fit picks on its own
to make the data fit better — and when allowed to, it picks something else
entirely:

| | slope a | constant b | b as a fraction of a | crosses 0.5 at |
|---|---|---|---|---|
| ours | 4.6149 | −2.3074 (**forced** = −a/2) | exactly −0.5 | p = 0.5000 |
| standard Platt | 4.3221 | −1.7828 (**chosen**) | −0.4125 | p = 0.4125 |

Given a = 4.3221, the constraint would have demanded b = −2.1610. The free fit
chose −1.7828 instead, because that fits the data better — and in doing so it
slid the crossing point to 0.4125, which is the decision/display contradiction
from the entry above.

**The geometry.** On the log-odds scale calibration is just a straight line,
z = a·p + b, with two degrees of freedom: how steep it is, and how high it sits.
Ours nails the line through the point (0.5, 0) and lets only the slope pivot
around it — a line on a hinge, free to rotate, not to slide. Standard Platt lets
it do both.

So the precise statement isn't "we set b to zero". It's **b = −a/2** — a
constraint linking the two, not a fixed value. Writing it as `fit_intercept=False`
on the centred score is simply the tidy way to express that, and it's why the
count is *one* fitted parameter (4.6149) against Platt's *two* (4.3221, −1.7828).

Which also answers it empirically: if centring were quietly supplying an
intercept, we'd have two free parameters and the mean predicted probability would
match the base rate for free. It doesn't — 0.5566 against 0.6327.

### "Centred on 0.5" — one fight, every number explained

Take a fight where the model's raw score for the red-corner fighter is
**p = 0.65**. The shipped calibrator (13 Sep 2026 artifact) has one learned
number, **β = 4.6149**, and no intercept. Here is the whole calculation.

**Step 1 — centre: `x = p − 0.5`**

```
x = 0.65 − 0.5 = +0.15
```

| number | what it is |
|---|---|
| `0.65` | the ensemble's raw output: "65% red wins" |
| `0.5` | the neutral score — a coin flip, and the training prior (`mirror_fights()` makes the training set exactly 50/50) |
| `+0.15` | the *lean*: 15 points toward red. Sign carries the direction (negative would mean toward blue); size carries how strong |

"Centred on 0.5" means **this subtraction and nothing more**: the calibrator is
fitted on, and later fed, `p − 0.5` instead of `p`. That is the literal code,
`calibrator.fit((oof_proba.values - 0.5).reshape(-1, 1), oof_y.values)` in
the notebook and `predict_proba([[raw_proba - 0.5]])` in `predict.py`.

**Step 2 — scale: `z = β · x`**

```
z = 4.6149 × 0.15 = +0.6922
```

| number | what it is |
|---|---|
| `4.6149` | β, the only fitted parameter: how many log-odds one point of lean is worth. Fitted on 7,869 pooled walk-forward OOF fights |
| `+0.6922` | the calibrated **log-odds** for red. Un-log it: e^0.6922 = 1.998, so red wins about 2 times for every 1 loss — odds of 2:1 |

**Step 3 — squash back to a probability: `σ(z) = 1 / (1 + e^−z)`**

```
e^−0.6922 = 0.5005
calibrated = 1 / (1 + 0.5005) = 0.6665
```

| number | what it is |
|---|---|
| `0.5005` | e^−z: the odds *against* red, 1 loss per 2 wins |
| `0.6665` | the calibrated probability. 2 wins / (2 wins + 1 loss) = 2/3 — same answer as the odds reading |

So **0.65 → 0.6665**: a stretch of +0.0165. β > 4 means "you were slightly
under-confident, lean a touch harder".

**Now the same fight with the corners swapped.** Raw score for blue-listed-first
is 0.35:

```
x = 0.35 − 0.5 = −0.15         (same lean, opposite sign)
z = 4.6149 × −0.15 = −0.6922   (same log-odds, opposite sign)
calibrated = 1 / (1 + e^0.6922) = 1 / (1 + 1.998) = 0.3335
```

And 0.6665 + 0.3335 = **1.0000**. That is the guarantee centring buys: because
x flips sign when the corners swap, and σ(−z) = 1 − σ(z), the two orientations
always sum to one.

**And the fight the model can't call.** Raw 0.5:

```
x = 0.5 − 0.5 = 0
z = 4.6149 × 0 = 0
calibrated = 1 / (1 + e^0) = 1 / 2 = 0.5
```

Note β never mattered in that line — `β × 0 = 0` whatever β is. That is what
"raw 0.5 maps to calibrated 0.5 exactly" means: the anchor is arithmetic, not a
fitted coincidence.

**What goes wrong without the subtraction.** Fit the identical no-intercept
model on `p` instead of `p − 0.5` (checked on the same OOF pool) and β comes
out **1.3200**. The fixed point is now wherever the input is zero — which is
p = 0, not p = 0.5:

| raw p | centred: x, z, calibrated | uncentred: z = 1.32·p, calibrated |
|---|---|---|
| 0.00 | −0.50, −2.307, **0.0905** | 0.000, **0.5000** |
| 0.35 | −0.15, −0.692, 0.3335 | 0.462, 0.6135 |
| 0.50 | 0.00, 0.000, **0.5000** | 0.660, **0.6593** |
| 0.65 | +0.15, +0.692, 0.6665 | 0.858, 0.7022 |
| 1.00 | +0.50, +2.307, 0.9095 | 1.320, 0.7892 |

Read the uncentred column: a fight the model is *certain* red loses (0.00)
displays as a coin flip, a genuine coin flip (0.50) displays as 66% red, and the
0.35 / 0.65 pair sums to 1.316, not 1 — the model now contradicts itself
depending on which fighter is listed first. Every number in that column is
above 0.5, so it would call red the favourite in every fight on the card.

**In one sentence:** centring on 0.5 re-expresses the raw score as a signed
distance from the coin-flip point, so that the no-intercept calibrator's
built-in fixed point (input 0 → output 0.5) lands on the neutral score rather
than on p = 0.

### So without centring, a coin flip favours red?

Yes — a raw 0.5 comes out at 0.659 for red — and it's worse than a lean:
**every** fight comes out red-favoured.

The reason is structural, not learned. With no intercept the calibrator is
σ(β · input), and the only point it can pin is input 0 → output 0.5. Uncentred,
input 0 is raw p = 0, so "red certainly loses" becomes a coin flip. β must be
positive (a higher raw score does go with more red wins), so every raw score
above 0 maps above 0.5 — the map physically cannot produce a blue-favoured
number. The fitted β of 1.32 is the least-bad compromise: a shallow slope that
squashes everything into 0.5–0.79 rather than pushing it anywhere sensible.

That makes it a different beast from the intercept case above. An intercept-ful
fit maps 0.5 → 0.594 because it has *read the 63% red base rate off the
training labels*. The uncentred no-intercept fit maps 0.5 → 0.659 without
consulting a base rate at all — its anchor is simply welded to the wrong end of
the scale. Two different failures; centring plus no intercept is the only
combination that avoids both.

For the record, the uncentred version never shipped — it's the hypothetical
that shows why the subtraction is there. The bug that did ship was the
intercept-ful one that moved the crossing point to 0.61.
