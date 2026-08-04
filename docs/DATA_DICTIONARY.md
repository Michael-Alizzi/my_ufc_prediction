# Data Dictionary

What every column family means, where it comes from, and what NaN means
there. Updated in the same commit as any data/feature change (CLAUDE.md →
Experiment protocol). Naming convention throughout: `r_*`/`b_*` = red/blue
corner, `*_diff` = red minus blue, `avg_*`/`med_*` = career EWM
mean/median of a per-fight stat. Every corner feature exists as an
`r_`/`b_` pair (mirroring requires it; a test enforces it).

## 1. Raw inputs (produced by the sibling scraper, copied to repo root)

| File | Grain | Key columns |
|---|---|---|
| `raw_fight_data.csv` (`;`-delimited) | one row per fight | fighter names, date, location, winner, win_by (method), last_round, last_round_time, format, referee, per-corner totals: KD, SIG_STR (x of y), TOTAL_STR, TD, SUB_ATT, REV, CTRL (m:ss), head/body/leg + distance/clinch/ground breakdowns |
| `raw_fighter_details.csv` | one row per fighter | fighter_name, Height, Weight, Reach, Stance, DOB, **Country** (Wikidata citizenship, `;`-joined for dual citizens; added Aug 2026 — older CSVs lack it and home-crowd features go NaN) |

## 2. Cleaned per-fight columns (notebook cells 6–12)

`date_d` (datetime), `weight_class` (ordered category), `gender`,
`title_fight` (0/1), `total_round_number` (3/5), `total_minutes`,
`last_round`, `last_round_time` (minutes, float), `win_by`, `winner`
(lowercased name), `location`; per-corner `*_lnd`/`*_att` splits of every
"x of y" stat plus `*_frac` accuracy fractions; fighter bio merges:
`r_/b_height_cm`, `weight_kg`, `reach_cm`, `stance`, `age`, `country`.
Draws are dropped (no label). ~950 phantom duplicate rows from 1990s
tournament nights are deduplicated on (r_fighter, b_fighter, date).

## 3. Engineered feature families (all prior-fights-only; NaN = no prior data)

| Family | Columns | Definition |
|---|---|---|
| Career averages | `avg_r_*`, `avg_b_*`, `avg_*_diff` | EWM mean (wall-clock halflife = 3 years) of each per-fight stat over PRIOR fights |
| Career medians | `med_r_*` … | rolling median twin; members correlating > 0.95 with their mean twin (pre-holdout) are dropped |
| Form | `r_/b_prev_win`, `prev_3_win`, `win_streak`, `lose_streak` (+diffs) | last-fight result, last-3, current streaks |
| Record | `r_/b_current_wins/losses`, `current_win_frac` (+diff) | prior UFC record |
| Activity | `r_/b_days_since_last`, `fights_last_365` (+diff) | layoff and fight frequency |
| Physique | `height_cm`, `weight_kg`, `reach_cm`, `bmi`, `age`, `stance` (+diffs) | from fighter details; ages computed at fight date |
| Finish profile | `r_/b_ko_win_rate`, `sub_win_rate`, `ko_loss_rate`, `sub_loss_rate` (+diffs) | share of prior fights won/lost by KO / submission, **shrunk** toward the weight class's pre-holdout base rate with K=5 pseudo-fights (`(K·p_wc + count)/(K + n)`, METHODOLOGY §6); debuts get the pure class prior, so these are never NaN |
| First-round wins | `r_/b_first_round_wins` (+diff) | career count of round-1 wins |
| Fight-time profile | `r_/b_avg_win_time`, `avg_loss_time` (+diffs) | mean minutes-into-the-fight at which prior wins/losses arrived (full earlier rounds + final-round clock) |
| Head-to-head | `h2h_fight_count`, `r_/b_h2h_wins`, `h2h_win_diff` | prior meetings of this exact pair |
| Elo | `r_/b_elo`, `elo_diff` | pre-fight Elo (K=32, start 1500), sequential update |
| Rules era | `rules_era` | shared ordinal: 0 pre-unified, 1 unified rules (Apr 2001), 2 post-2017 revision; pinned to 2 at predict time |
| Home crowd | `r_/b_home_crowd`, `home_crowd_diff` | 1 if any citizenship matches the event country, 0 if none, NaN unknown; supplied per-prediction via `event_country`, never inherited from a past fight |

Shared context columns (no r/b pair, untouched by mirroring): `gender`,
`weight_class`, `title_fight`, `total_round_number`, `total_minutes`,
`rules_era`.

## 4. Exported artifacts

**`ensemble.joblib`** (written by the Threshold Selection cell):

| Key | Contents |
|---|---|
| `models` | list of 3 refit XGBoost classifiers (top Optuna trials) |
| `lgbm`, `lgbm_weight` | LightGBM model and its validation-chosen blend weight |
| `best_th` | decision threshold (fixed 0.5) |
| `calibrator` | centered no-intercept Platt logistic (display only) |
| `feature_names`, `dtypes` | training matrix schema (order + dtypes incl. categoricals) |
| `diff_pairs` | exact `{diff_col: (r_col, b_col)}` source map, verified `d = r − b` at export |
| `train_end`, `data_max_date` | provenance: training cutoff and data recency |
| `oof` | pooled walk-forward OOF predictions with fight identity (`r_fighter`, `b_fighter`, `date_d`, `y`, `proba`) — the next run's high-power paired comparison aligns on this |

**`fighter_history.parquet`**: the full engineered frame (one row per
fight, every column above), date-sorted with `fight_id` reassigned
chronologically at export. Serving uses it for per-fighter last-row lookups
and head-to-head counts. Loading either artifact executes pickle-family
code — only load the repo's own committed files.

**`ensemble_baseline.joblib`** (gitignored): manual snapshot
(`cp ensemble.joblib ensemble_baseline.joblib`) taken before an experiment;
the Paired Comparison cell reads it.

## 5. Weekly outputs (`weekly-predictions-log` branch)

`predictions_output.md` — the card's predictions, confidences, and the $100
Kelly split. `card.json` — the exact card + odds used, committed beside it
so any future model can replay the same card mechanically ($100 replay
metric; see EXPERIMENTS.md). Skip-unchanged-retrain logic diffs the freshly
scraped CSVs against the committed copies (the raw CSVs are tracked in git
since Aug 2026).
