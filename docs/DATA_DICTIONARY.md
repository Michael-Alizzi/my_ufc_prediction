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
| Career averages | `avg_r_*`, `avg_b_*`, `avg_*_diff` | EWM mean (fight-count halflife = 5 fights, EXPERIMENTS.md entry 3) of each per-fight stat over PRIOR fights |
| Career medians | `med_r_*` … | rolling median twin; members correlating > 0.95 with their mean twin (pre-holdout) are dropped |
| Absorbed averages | `avg_r_abs_*`, `avg_b_abs_*`, `avg_abs_*_diff` | same EWM over what OPPONENTS did to the fighter in PRIOR fights — six stats (kd, sig_str_lnd, total_str_lnd, td_lnd, ctrl, sub_att): durability/defense (METHODOLOGY §4.1, entry 6) |
| Opponent-adjusted averages | `avg_r_adj_*`, `avg_b_adj_*`, `avg_adj_*_diff` | same EWM over per-fight output MINUS that opponent's prior allowed average (their `abs` EWM) — same six stats: production relative to the defense actually faced (METHODOLOGY §4.2, entry 7) |
| Form | `r_/b_prev_win`, `prev_3_win`, `win_streak`, `lose_streak` (+diffs) | last-fight result, last-3, current streaks |
| Record | `r_/b_current_wins/losses`, `current_win_frac` (+diff) | prior UFC record |
| Activity | `r_/b_days_since_last`, `fights_last_365` (+diff) | layoff and fight frequency |
| Physique | `height_cm`, `weight_kg`, `reach_cm`, `bmi`, `age`, `stance` (+diffs) | from fighter details; ages computed at fight date |
| Finish profile | `r_/b_ko_win_rate`, `sub_win_rate`, `ko_loss_rate`, `sub_loss_rate` (+diffs) | share of prior fights won/lost by KO / submission |
| First-round wins | `r_/b_first_round_wins` (+diff) | career count of round-1 wins |
| Fight-time profile | `r_/b_avg_win_time`, `avg_loss_time` (+diffs) | mean minutes-into-the-fight at which prior wins/losses arrived (full earlier rounds + final-round clock) |
| Head-to-head | `h2h_fight_count`, `r_/b_h2h_wins`, `h2h_win_diff` | prior meetings of this exact pair |
| Elo | `r_/b_elo`, `elo_diff` | pre-fight Elo (K=32, start 1500), sequential update |
| Rules era | `rules_era` | shared ordinal: 0 pre-unified, 1 unified rules (Apr 2001), 2 post-2017 revision; pinned to 2 at predict time |
| Home crowd | `r_/b_home_crowd`, `home_crowd_diff` | 1 if any citizenship matches the event country, 0 if none, NaN unknown; supplied per-prediction via `event_country`, never inherited from a past fight |
| Market probability | `r_/b_market_prob` | vig-free implied win probability from the fight's closing odds (METHODOLOGY §6); training values joined from the local, never-committed `odds_train.csv` (desktop, `scripts/odds_backtest.py --export-training`), serving values from the odds supplied per-prediction; NaN when no odds exist |

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

`predictions_output.md` — the card's predictions, confidences, and the
bankroll's Kelly split (rule A) plus C/E shadow columns. `card.json` — the
exact card + odds used (two-slot: `odds1/2` Sportsbet staking prices,
`feat_odds1/2` de-vigged AU-median feature input), committed beside it so
any future model can replay the same card mechanically (replay metric; see
EXPERIMENTS.md). `ledger.md` — per-event graded returns for rules A/C/E
(`scripts/score_card.py`; the entry-9 10-event promotion record).
`collected_odds.csv` — phase-2 own-odds feed, one row per fight
(`r_fighter`, `b_fighter`, `date_d`, `odds_r`, `odds_b`), merged into
`odds_train.csv` by `scripts/fetch_training_odds.py` at retrain time.
Skip-unchanged-retrain logic diffs the freshly scraped CSVs against the
committed copies (the raw CSVs are tracked in git since Aug 2026).

## 6. Complete column inventory (auto-generated)

Every literal column name, so nothing has to be inferred from the family
descriptions above. Paired columns are listed once: an `r_`/`b_` pair like
`r_elo`+`b_elo` appears as `elo`, and a career aggregate like
`avg_r_kd`+`avg_b_kd` appears under its `avg_`/`med_` group as `kd`.
Regenerate after any retrain with the snippet at the end.

### raw_fight_data.csv (41 columns, `;`-separated)

`R_fighter` `B_fighter` `R_KD` `B_KD` `R_SIG_STR.` `B_SIG_STR.` `R_SIG_STR_pct` `B_SIG_STR_pct` `R_TOTAL_STR.` `B_TOTAL_STR.` `R_TD` `B_TD` `R_TD_pct` `B_TD_pct` `R_SUB_ATT` `B_SUB_ATT` `R_REV` `B_REV` `R_CTRL` `B_CTRL` `R_HEAD` `B_HEAD` `R_BODY` `B_BODY` `R_LEG` `B_LEG` `R_DISTANCE` `B_DISTANCE` `R_CLINCH` `B_CLINCH` `R_GROUND` `B_GROUND` `win_by` `last_round` `last_round_time` `Format` `Referee` `date` `location` `Fight_type` `Winner`

### raw_fighter_details.csv (14 columns)

`fighter_name` `Height` `Weight` `Reach` `Stance` `DOB` `SLpM` `Str_Acc` `SApM` `Str_Def` `TD_Avg` `TD_Acc` `TD_Def` `Sub_Avg`

### fighter_history.parquet (344 columns)

**Per-corner pairs `r_*`/`b_*` (60 pairs = 120 columns):**

`age` `avg_loss_time` `avg_win_time` `bmi` `body_att` `body_frac` `body_lnd` `clinch_att` `clinch_frac` `clinch_lnd` `country` `ctrl` `current_losses` `current_win_frac` `current_wins` `days_since_last` `distance_att` `distance_frac` `distance_lnd` `dob_d` `elo` `fighter` `fights_last_365` `first_round_wins` `ground_att` `ground_frac` `ground_lnd` `h2h_wins` `head_att` `head_frac` `head_lnd` `height_cm` `home_crowd` `kd` `ko_loss_rate` `ko_win_rate` `leg_att` `leg_frac` `leg_lnd` `lose_streak` `market_prob` `prev_3_win` `prev_win` `reach_cm` `rev` `sig_str_att` `sig_str_frac` `sig_str_lnd` `stance` `sub_att` `sub_loss_rate` `sub_win_rate` `td_att` `td_frac` `td_lnd` `total_str_att` `total_str_frac` `total_str_lnd` `weight_kg` `win_streak`

**Career averages `avg_r_*`/`avg_b_*` (43 stats = 86 columns):**

`abs_ctrl` `abs_kd` `abs_sig_str_lnd` `abs_sub_att` `abs_td_lnd` `abs_total_str_lnd` `adj_ctrl` `adj_kd` `adj_sig_str_lnd` `adj_sub_att` `adj_td_lnd` `adj_total_str_lnd` `body_att` `body_frac` `body_lnd` `clinch_att` `clinch_frac` `clinch_lnd` `ctrl` `distance_att` `distance_frac` `distance_lnd` `ground_att` `ground_frac` `ground_lnd` `head_att` `head_frac` `head_lnd` `kd` `leg_att` `leg_frac` `leg_lnd` `rev` `sig_str_att` `sig_str_frac` `sig_str_lnd` `sub_att` `td_att` `td_frac` `td_lnd` `total_str_att` `total_str_frac` `total_str_lnd`

**Career medians `med_r_*`/`med_b_*` (31 stats = 62 columns):**

`body_att` `body_frac` `body_lnd` `clinch_att` `clinch_frac` `clinch_lnd` `ctrl` `distance_att` `distance_frac` `distance_lnd` `ground_att` `ground_frac` `ground_lnd` `head_att` `head_frac` `head_lnd` `kd` `leg_att` `leg_frac` `leg_lnd` `rev` `sig_str_att` `sig_str_frac` `sig_str_lnd` `sub_att` `td_att` `td_frac` `td_lnd` `total_str_att` `total_str_frac` `total_str_lnd`

**Matchup diffs, red minus blue (58):**

`age_diff` `avg_abs_ctrl_diff` `avg_abs_kd_diff` `avg_abs_sig_str_lnd_diff` `avg_abs_sub_att_diff` `avg_abs_td_lnd_diff` `avg_abs_total_str_lnd_diff` `avg_adj_ctrl_diff` `avg_adj_kd_diff` `avg_adj_sig_str_lnd_diff` `avg_adj_sub_att_diff` `avg_adj_td_lnd_diff` `avg_adj_total_str_lnd_diff` `avg_body_frac_diff` `avg_clinch_frac_diff` `avg_ctrl_diff` `avg_distance_frac_diff` `avg_ground_frac_diff` `avg_head_frac_diff` `avg_kd_diff` `avg_leg_frac_diff` `avg_loss_time_diff` `avg_rev_diff` `avg_sig_str_frac_diff` `avg_sub_att_diff` `avg_td_frac_diff` `avg_total_str_frac_diff` `avg_win_time_diff` `bmi_diff` `current_win_frac_diff` `elo_diff` `fights_last_365_diff` `first_round_wins_diff` `h2h_win_diff` `height_diff` `home_crowd_diff` `ko_loss_rate_diff` `ko_win_rate_diff` `lose_streak_diff` `med_body_frac_diff` `med_clinch_frac_diff` `med_ctrl_diff` `med_distance_frac_diff` `med_ground_frac_diff` `med_head_frac_diff` `med_kd_diff` `med_leg_frac_diff` `med_rev_diff` `med_sig_str_frac_diff` `med_sub_att_diff` `med_td_frac_diff` `med_total_str_frac_diff` `prev_win_diff` `reach_diff` `sub_loss_rate_diff` `sub_win_rate_diff` `weight_diff` `win_streak_diff`

**Everything else (18):**

`win_by` `last_round` `last_round_time` `referee` `location` `winner` `total_round_number` `total_minutes` `date_d` `weight_class` `gender` `title_fight` `fighter_name_x` `fighter_name_y` `fight_id` `h2h_fight_count` `rules_era` `r_win`

### Model feature schema — ensemble.joblib `feature_names` (265 features)

**Per-corner pairs `r_*`/`b_*` (26 pairs = 52 columns):**

`age` `avg_loss_time` `avg_win_time` `bmi` `current_losses` `current_win_frac` `current_wins` `days_since_last` `elo` `fights_last_365` `first_round_wins` `h2h_wins` `height_cm` `home_crowd` `ko_loss_rate` `ko_win_rate` `lose_streak` `market_prob` `prev_3_win` `prev_win` `reach_cm` `stance` `sub_loss_rate` `sub_win_rate` `weight_kg` `win_streak`

**Career averages `avg_r_*`/`avg_b_*` (43 stats = 86 columns):**

`abs_ctrl` `abs_kd` `abs_sig_str_lnd` `abs_sub_att` `abs_td_lnd` `abs_total_str_lnd` `adj_ctrl` `adj_kd` `adj_sig_str_lnd` `adj_sub_att` `adj_td_lnd` `adj_total_str_lnd` `body_att` `body_frac` `body_lnd` `clinch_att` `clinch_frac` `clinch_lnd` `ctrl` `distance_att` `distance_frac` `distance_lnd` `ground_att` `ground_frac` `ground_lnd` `head_att` `head_frac` `head_lnd` `kd` `leg_att` `leg_frac` `leg_lnd` `rev` `sig_str_att` `sig_str_frac` `sig_str_lnd` `sub_att` `td_att` `td_frac` `td_lnd` `total_str_att` `total_str_frac` `total_str_lnd`

**Career medians `med_r_*`/`med_b_*` (31 stats = 62 columns):**

`body_att` `body_frac` `body_lnd` `clinch_att` `clinch_frac` `clinch_lnd` `ctrl` `distance_att` `distance_frac` `distance_lnd` `ground_att` `ground_frac` `ground_lnd` `head_att` `head_frac` `head_lnd` `kd` `leg_att` `leg_frac` `leg_lnd` `rev` `sig_str_att` `sig_str_frac` `sig_str_lnd` `sub_att` `td_att` `td_frac` `td_lnd` `total_str_att` `total_str_frac` `total_str_lnd`

**Matchup diffs, red minus blue (58):**

`age_diff` `avg_abs_ctrl_diff` `avg_abs_kd_diff` `avg_abs_sig_str_lnd_diff` `avg_abs_sub_att_diff` `avg_abs_td_lnd_diff` `avg_abs_total_str_lnd_diff` `avg_adj_ctrl_diff` `avg_adj_kd_diff` `avg_adj_sig_str_lnd_diff` `avg_adj_sub_att_diff` `avg_adj_td_lnd_diff` `avg_adj_total_str_lnd_diff` `avg_body_frac_diff` `avg_clinch_frac_diff` `avg_ctrl_diff` `avg_distance_frac_diff` `avg_ground_frac_diff` `avg_head_frac_diff` `avg_kd_diff` `avg_leg_frac_diff` `avg_loss_time_diff` `avg_rev_diff` `avg_sig_str_frac_diff` `avg_sub_att_diff` `avg_td_frac_diff` `avg_total_str_frac_diff` `avg_win_time_diff` `bmi_diff` `current_win_frac_diff` `elo_diff` `fights_last_365_diff` `first_round_wins_diff` `h2h_win_diff` `height_diff` `home_crowd_diff` `ko_loss_rate_diff` `ko_win_rate_diff` `lose_streak_diff` `med_body_frac_diff` `med_clinch_frac_diff` `med_ctrl_diff` `med_distance_frac_diff` `med_ground_frac_diff` `med_head_frac_diff` `med_kd_diff` `med_leg_frac_diff` `med_rev_diff` `med_sig_str_frac_diff` `med_sub_att_diff` `med_td_frac_diff` `med_total_str_frac_diff` `prev_win_diff` `reach_diff` `sub_loss_rate_diff` `sub_win_rate_diff` `weight_diff` `win_streak_diff`

**Everything else (7):**

`gender` `weight_class` `title_fight` `total_round_number` `total_minutes` `h2h_fight_count` `rules_era`

### odds files

`odds_train.csv` and `collected_odds.csv` share one schema: `r_fighter` `b_fighter` `date_d` `odds_r` `odds_b` (decimal closing odds, vig included).

### Regenerating this section

```python
# repo root, after a retrain — raw column dumps to re-group by the same rules
import pandas as pd, joblib
print(pd.read_csv("raw_fight_data.csv", nrows=1, sep=";").columns.tolist())
print(pd.read_parquet("fighter_history.parquet").columns.tolist())
print(joblib.load("ensemble.joblib")["feature_names"])
```
