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

### What are shadow rules C and E, and why are they logged but not staked?

Entry 9 backtested five staking rules on 5,786 historical fights. Rule A won on the
pre-registered criteria, but two losers looked suspiciously good:

- **C ("vig floor")** — A, but an edge must exceed that fight's bookmaker margin
  (the vig, typically ~5–6%): edges smaller than the margin are treated as noise.
  Fewer, more selective bets.
- **E ("shrunk staking")** — average the model's probability 50/50 with the
  market's vig-free implied probability *before* computing edge and stakes. Only
  bets where value survives conceding the market is half right; tames Kelly's
  oversized stakes exactly where the model disagrees hardest with the market.

Both beat A on parts of the backtest (E's Kelly ROI was +27.9% vs A's +14.0%, and
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

### Why is a card scored 5–6 days after it happens?

Cards run Saturday night US time — Sunday afternoon AEST — and the scoring Routine
runs Friday 6 PM AEST, so each card is graded the following Friday. Nothing decays
in the meantime (results are results), it just means the scoring notification isn't
same-weekend. Moving scoring to Sunday evening AEST would grade same-weekend if
that ever matters more than the Friday rhythm.

### Where do I see how the bets are going?

The **Octagon Ledger dashboard**:
<https://claude.ai/code/artifact/5d7c8637-557d-4ec2-981c-9255b986f52f> — a
Performance tab (cumulative return per rule across scored events, per-event
nets, hit rates, the 10-event promotion tally, and the entry-9 backtest
reference) with these docs as the other tabs. It is generated by
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
