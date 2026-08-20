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

### What runs when?

Two cloud Routines, both AEST, no PC involved:

- **Thursday 1 PM (card day):** scrape fresh fight data (when ufcstats allows) →
  fetch the upcoming card's Sportsbet + AU-median odds → predict, stake by rule A
  with C/E shadow logs → push `predictions_output.md` + `card.json` to the
  `weekly-predictions-log` branch → phone notification with the slip.
- **Friday 6 PM (scoring day):** find the most recent completed-but-unscored card,
  fetch results, grade A/C/E via `scripts/score_card.py` (voids handled), append
  `ledger.md` + `collected_odds.csv` on the log branch → phone notification with
  the result and the running promotion tally.

Retraining is **not** scheduled — see above.

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

On the **Experiments** tab specifically, "Net return" plots a **flat $1
per bet** (Aug 2026), not the actual $ staked: rules concentrate
differently — C typically puts its whole bankroll on one bet some weeks,
A spreads across several — so comparing rules on real dollars exaggerates
whichever one happens to concentrate more that card. Flat staking is the
same convention `scripts/betting_rule_compare.py` and History's backtest
replay already use for exactly this reason. This is presentational only:
the pre-registered promotion decision (EXPERIMENTS.md entries 9–10) is
still made on the real-$ bankroll-replay figures in the Rule comparison
table below the chart and in `ledger.md`'s own `Staked`/`Returned`/`Net`
columns, unchanged — the chart's flat view never feeds that decision.
**Performance**'s rule-A chart keeps real dollars throughout, since
that's what's actually staked. Marker size always reflects that event's real $ swing regardless
of which metric is on screen, and hovering a point shows all four
numbers together no matter which one is plotted.

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

### Where do I see how the bets are going?

The **Octagon Ledger dashboard**:
<https://claude.ai/code/artifact/5d7c8637-557d-4ec2-981c-9255b986f52f> — a
Performance tab (money view: P/L so far, rule-A chart, bankroll allocator,
past-events detail) and an Experiments tab (rule comparison, chart, and
backtest reference) with these docs as the other tabs. It is generated by
`scripts/build_dashboard.py` from `ledger.md`; the Friday scoring Routine
rebuilds and republishes it right after grading each card, so it is always
current as of the most recent scored event.

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
