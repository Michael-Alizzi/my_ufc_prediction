#!/usr/bin/env python3
"""Build dashboard.html: the betting-performance dashboard + docs, one file.

Reads ledger.md (the entry-9 A/C/E/F record appended by score_card.py on the
weekly-predictions-log branch), that branch's card.json history (current
card for the bankroll allocator, past commits for each event's per-fight
detail), and the three docs/*.md, emitting a single self-contained HTML
page: Performance (P/L so far, upcoming-card allocator, past-events
detail), Experiments (rule explainer + trajectory + comparison), History
(full backtest replay), and one tab per doc. No network access at view
time — the Monday scoring Routine regenerates the file and republishes it
as an Artifact after each card is graded.

Usage (from repo root, with ledger.md checked out of the log branch):
    python3 scripts/build_dashboard.py [--ledger ledger.md] [--out dashboard.html]

A missing/empty ledger is fine: Experiments renders its empty state
(backtest reference numbers + "first grading pending").
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import markdown

DOCS = [("faq", "FAQ", "docs/FAQ.md"),
        ("methodology", "Methodology", "docs/METHODOLOGY.md"),
        ("dictionary", "Data dictionary", "docs/DATA_DICTIONARY.md")]

ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|([^|]+)\|\s*([ACEF])\s*"
                 r"\|\s*\$([\d.]+)\s*\|\s*\$([\d.]+)\s*\|\s*([+-][\d.]+)\s*"
                 r"\|\s*(\d+)/(\d+)/(\d+)\s*\|(?:\s*([+-][\d.]+)\s*\|)?"
                 r"(?:\s*(?:([+-][\d.]+)%|-)\s*\|)?")


def parse_ledger(path):
    """ledger.md -> ordered event list with per-rule results."""
    events, index = [], {}
    if not os.path.exists(path):
        return events
    for line in open(path):
        m = ROW.match(line.strip())
        if not m:
            continue
        date, event, rule = m.group(1), m.group(2).strip(), m.group(3)
        key = (date, event)
        if key not in index:
            index[key] = {"date": date, "event": event, "rules": {}}
            events.append(index[key])
        net = float(m.group(6))
        # flat_net (profit at a flat $1/bet, stake-size-independent) is a
        # newer column; fall back to real net for rows written before it
        # existed so an old-format ledger still parses.
        flat_net = float(m.group(10)) if m.group(10) else net
        index[key]["rules"][rule] = {
            "staked": float(m.group(4)), "returned": float(m.group(5)),
            "net": net, "flat_net": flat_net, "won": int(m.group(7)),
            "placed": int(m.group(8)), "void": int(m.group(9)),
            # avg closing-line value (%), logged from the pre-fight odds
            # snapshot; None for events before the CLV change (Sep 2026)
            "clv": float(m.group(11)) if m.group(11) else None}
    return sorted(events, key=lambda e: e["date"])


def summarise(events):
    total = {r: {"staked": 0.0, "returned": 0.0, "won": 0, "placed": 0,
                 "void": 0, "ahead": 0, "flat_net": 0.0} for r in "ACEF"}
    for e in events:
        for r, row in e["rules"].items():
            t = total[r]
            for k in ("staked", "returned", "won", "placed", "void"):
                t[k] += row[k]
            t["flat_net"] += row["flat_net"]
            if r != "A" and "A" in e["rules"] and row["net"] > e["rules"]["A"]["net"]:
                t["ahead"] += 1
    for r, t in total.items():
        clvs = [e["rules"][r]["clv"] for e in events
                if r in e["rules"] and e["rules"][r]["clv"] is not None]
        t["clv"] = round(sum(clvs) / len(clvs), 1) if clvs else None
        t["net"] = round(t["returned"] - t["staked"], 2)
        t["flat_net"] = round(t["flat_net"], 2)
        t["roi"] = round(100 * t["net"] / t["staked"], 1) if t["staked"] else None
        t["hit"] = round(100 * t["won"] / t["placed"], 1) if t["placed"] else None
    return total


def git_show(ref):
    """Read a file from a git ref without touching the working tree or index
    (unlike `git checkout <ref> -- file`, which stages the file and has twice
    landed stray files on master via this script's own commits)."""
    import subprocess
    out = subprocess.run(["git", "show", ref], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def fetch_log_branch():
    import subprocess
    subprocess.run(["git", "fetch", "origin", "weekly-predictions-log"],
                   capture_output=True)


def _card_fights_rows(fights, preds):
    """Shared row-shaping for both next_card() and event_history(): drop
    unpredictable/oddsless fights, carry both corners' odds, the model's
    chosen side/price/kelly fraction (0 if no value)."""
    rows = []
    for p, f in zip(preds, fights):
        if p.get("prediction") in ("error", "no data") or not (f.get("odds1") and f.get("odds2")):
            continue
        rows.append({"f1": f["fighter1"], "f2": f["fighter2"],
                     "weight_class": p.get("weight_class", f.get("weight_class", "?")),
                     "pick": p.get("prediction"), "confidence": p.get("confidence"),
                     "odds1": float(f["odds1"]), "odds2": float(f["odds2"]),
                     "bet_on": p.get("bet_on"), "bet_odds": p.get("bet_odds"),
                     "kelly": p.get("kelly", 0), "stake": p.get("stake_amt", 0),
                     "shadow": p.get("shadow") or ""})
    return rows


def next_card(events, artifact_path="ensemble.joblib", history_path="fighter_history.parquet"):
    """The most recently logged card (weekly-predictions-log branch) with
    live odds and each fight's kelly fraction, for the Performance tab's
    bankroll allocator. None if nothing is logged yet or the artifacts this
    container needs aren't present."""
    fetch_log_branch()
    raw = git_show("origin/weekly-predictions-log:card.json")
    if not raw or not (os.path.exists(artifact_path) and os.path.exists(history_path)):
        return None
    fights = json.loads(raw)
    pred_md = git_show("origin/weekly-predictions-log:predictions_output.md") or ""
    title_m = re.search(r"^## UFC Predictions: (.+)$", pred_md, re.M)
    title = title_m.group(1) if title_m else "Upcoming card"
    bankroll_m = re.search(r"risking \$(\d+)", pred_md)
    bankroll = int(bankroll_m.group(1)) if bankroll_m else 50

    sys.path.insert(0, ".")
    from predict import load_artifacts, load_history
    from send_weekly_predictions import make_predictions
    # event_country isn't persisted anywhere the rebuild can recover, so
    # home-crowd features come back NaN here -- confidence can differ
    # slightly from the original run's; the caption says so.
    preds = make_predictions(fights, load_history(), load_artifacts(),
                             bankroll=bankroll)
    rows = _card_fights_rows(fights, preds)
    if not rows:
        return None
    # already scored? ledger event names are a prefix of the "(date)"-suffixed title
    decided = any(e["event"] in title for e in events)
    return {"event": title, "bankroll": bankroll, "decided": decided, "fights": rows}


def _event_rule_stats(fights, preds):
    """Per-rule (A/C/E/F) bet count and sum of market-implied win% for one
    event, parsed from the same `shadow` strings scripts/score_card.py
    grades from -- gives every rule (not just A) an odds trail for the
    bet-rate/avg-market-win% chart metrics. Returns (fights_offered, stats)."""
    stats = {r: {"bets": 0, "implied_sum": 0.0} for r in "ACEF"}
    offered = 0
    for p, f in zip(preds, fights):
        if p.get("prediction") in ("error", "no data") or not (f.get("odds1") and f.get("odds2")):
            continue
        offered += 1
        if p.get("bet_on") and p.get("bet_odds"):
            stats["A"]["bets"] += 1
            stats["A"]["implied_sum"] += 100.0 / p["bet_odds"]
        for part in (p.get("shadow") or "").split(" / "):
            if part.startswith(("C:", "E:", "F:")):
                try:
                    odds = float(part.split("(@")[1].rstrip(")"))
                except (IndexError, ValueError):
                    continue
                rule = part[0]
                stats[rule]["bets"] += 1
                stats[rule]["implied_sum"] += 100.0 / odds
    return offered, stats


def event_history(events, artifact_path="ensemble.joblib", history_path="fighter_history.parquet"):
    """Per-fight betting detail AND per-rule aggregate stats (bet count,
    avg market-implied win%, fights offered) for every ledger event: which
    card.json posted it (walking weekly-predictions-log's history, since
    the branch's HEAD has usually moved on to a newer card by the time this
    builds), replayed through the exact same prediction code. Returns
    ({} , {}) if artifacts are missing; an event with no matching commit is
    silently skipped in both (its row renders "detail unavailable")."""
    if not events or not (os.path.exists(artifact_path) and os.path.exists(history_path)):
        return {}, {}
    import subprocess
    fetch_log_branch()
    log = subprocess.run(["git", "log", "--format=%H", "origin/weekly-predictions-log",
                          "--", "card.json"], capture_output=True, text=True)
    shas = [s for s in log.stdout.split() if s] if log.returncode == 0 else []
    if not shas:
        return {}, {}

    sys.path.insert(0, ".")
    from predict import load_artifacts, load_history
    from send_weekly_predictions import make_predictions
    artifacts, history = load_artifacts(), load_history()

    detail, stats = {}, {}
    for e in events:
        match_sha, match_pred = None, None
        for sha in shas:  # newest first -> first hit = most recent posting of this card
            pred = git_show(f"{sha}:predictions_output.md") or ""
            if e["event"] in pred:
                match_sha, match_pred = sha, pred
                break
        if not match_sha:
            continue
        raw = git_show(f"{match_sha}:card.json")
        if not raw:
            continue
        fights = json.loads(raw)
        bankroll_m = re.search(r"risking \$(\d+)", match_pred)
        bankroll = int(bankroll_m.group(1)) if bankroll_m else 50
        preds = make_predictions(fights, history, artifacts, bankroll=bankroll)
        key = e["date"] + "|" + e["event"]
        detail[key] = _card_fights_rows(fights, preds)
        offered, rule_stats = _event_rule_stats(fights, preds)
        stats[key] = {"offered": offered, "rules": rule_stats}
    return detail, stats


def backtest(odds_path, artifact_path):
    """Replay entry 9's arms A/C/E bet-by-bet over the pooled-OOF fights
    matched to historical closing odds. Returns None when the inputs aren't
    present (odds_train.csv is gitignored — mma-ai upstream is unlicensed —
    so it must be rebuilt via scripts/fetch_training_odds.py per container).
    Rule definitions mirror scripts/betting_rule_compare.py exactly."""
    if not (os.path.exists(odds_path) and os.path.exists(artifact_path)):
        return None
    import joblib
    import pandas as pd
    sys.path.insert(0, ".")
    from predict import kelly_edge
    oof = joblib.load(artifact_path)["oof"].copy()
    oof["date_d"] = pd.to_datetime(oof["date_d"])
    odds = pd.read_csv(odds_path, parse_dates=["date_d"])
    df = (oof.merge(odds, on=["r_fighter", "b_fighter", "date_d"])
             .sort_values("date_d"))

    import math
    lam = 0.746  # rule F model-trust weight (entry 10; frozen)
    logit = lambda x: math.log(x / (1 - x))  # noqa: E731
    bets = {"A": [], "C": [], "E": [], "F": []}
    for r in df.itertuples():
        k_r, k_b = kelly_edge(r.proba, r.odds_r), kelly_edge(1 - r.proba, r.odds_b)
        imp_r_vf = (1 / r.odds_r) / (1 / r.odds_r + 1 / r.odds_b)
        vig = 1 / r.odds_r + 1 / r.odds_b - 1
        date = r.date_d.strftime("%Y-%m-%d")

        def row(on_red, k, rule):
            on, vs = ((r.r_fighter, r.b_fighter) if on_red
                      else (r.b_fighter, r.r_fighter))
            odds_ = r.odds_r if on_red else r.odds_b
            won = int(bool(r.y) == on_red)
            k = round(min(k, 0.25), 4)
            if rule == "A":  # names only where the table shows them
                return [date, on.title(), vs.title(), round(odds_, 2), k, won]
            return [date, round(odds_, 2), k, won]

        if k_r > 0 or k_b > 0:
            bets["A"].append(row(k_r > 0, k_r if k_r > 0 else k_b, "A"))
        edge_r, edge_b = r.proba * r.odds_r - 1, (1 - r.proba) * r.odds_b - 1
        if max(edge_r, edge_b) > vig:
            on_red = edge_r > edge_b
            bets["C"].append(row(on_red, k_r if on_red else k_b, "C"))
        ps = (r.proba + imp_r_vf) / 2
        ks_r, ks_b = kelly_edge(ps, r.odds_r), kelly_edge(1 - ps, r.odds_b)
        if ks_r > 0 or ks_b > 0:
            bets["E"].append(row(ks_r > 0, ks_r if ks_r > 0 else ks_b, "E"))
        pc = min(max(r.proba, 1e-6), 1 - 1e-6)
        pf = 1 / (1 + math.exp(-(lam * logit(pc) + (1 - lam) * logit(imp_r_vf))))
        kf_r, kf_b = kelly_edge(pf, r.odds_r), kelly_edge(1 - pf, r.odds_b)
        if kf_r > 0 or kf_b > 0:
            bets["F"].append(row(kf_r > 0, kf_r if kf_r > 0 else kf_b, "F"))
    return {"fights": len(df), "span": [df["date_d"].min().strftime("%Y-%m-%d"),
                                        df["date_d"].max().strftime("%Y-%m-%d")],
            "fights_by_year": {str(y): int(n) for y, n in
                               df["date_d"].dt.year.value_counts().items()},
            "fights_by_month": {str(m): int(n) for m, n in
                                df["date_d"].dt.strftime("%Y-%m").value_counts().items()},
            "bets": bets}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="ledger.md")
    ap.add_argument("--odds", default="odds_train.csv")
    ap.add_argument("--artifact", default="ensemble.joblib")
    ap.add_argument("--out", default="dashboard.html")
    args = ap.parse_args()

    events = parse_ledger(args.ledger)
    data = {"events": events, "totals": summarise(events)}
    hist = backtest(args.odds, args.artifact)
    upcoming = next_card(events, args.artifact)
    event_detail, event_stats = event_history(events, args.artifact)

    md = markdown.Markdown(extensions=["tables", "fenced_code"])
    docs_html = {key: md.reset().convert(open(path).read()) if os.path.exists(path)
                 else "<p>missing " + path + "</p>" for key, _, path in DOCS}
    # Cross-doc links become tab switches; repo-relative links go to GitHub.
    repo = "https://github.com/Michael-Alizzi/my_ufc_prediction/blob/master/"
    for key, html in docs_html.items():
        docs_html[key] = (html
                          .replace('href="FAQ.md"', 'href="#faq"')
                          .replace('href="METHODOLOGY.md"', 'href="#methodology"')
                          .replace('href="DATA_DICTIONARY.md"', 'href="#dictionary"')
                          .replace('href="../', 'href="' + repo))

    aest = datetime.now(timezone(timedelta(hours=10)))
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(data))
            .replace("__HIST__", json.dumps(hist))
            .replace("__NEXT__", json.dumps(upcoming))
            .replace("__EVENT_DETAIL__", json.dumps(event_detail))
            .replace("__EVENT_STATS__", json.dumps(event_stats))
            .replace("__UPDATED__", aest.strftime("%-d %b %Y, %-I:%M %p AEST"))
            .replace("__FAQ__", docs_html["faq"])
            .replace("__METHODOLOGY__", docs_html["methodology"])
            .replace("__DICTIONARY__", docs_html["dictionary"]))
    open(args.out, "w").write(html)
    print(f"wrote {args.out}: {len(events)} scored event(s), "
          f"backtest {'%d fights' % hist['fights'] if hist else 'ABSENT'}")


TEMPLATE = r"""<title>Octagon Ledger</title>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
    --muted: #898781; --grid: #e1e0d9; --axis: #c3c2b7;
    --border: rgba(11,11,11,0.10);
    --sA: #2a78d6; --sC: #eb6834; --sE: #1baf7a; --sF: #eda100;
    --good: #006300; --bad: #d03b3b; --chip: #f0efec;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
      --muted: #898781; --grid: #2c2c2a; --axis: #383835;
      --border: rgba(255,255,255,0.10);
      --sA: #3987e5; --sC: #d95926; --sE: #199e70; --sF: #c98500;
      --good: #0ca30c; --bad: #e66767; --chip: #262624;
    }
  }
  :root[data-theme="dark"] {
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
    --muted: #898781; --grid: #2c2c2a; --axis: #383835;
    --border: rgba(255,255,255,0.10);
    --sA: #3987e5; --sC: #d95926; --sE: #199e70; --sF: #c98500;
    --good: #0ca30c; --bad: #e66767; --chip: #262624;
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  body { background: var(--page); color: var(--ink); margin: 0;
         font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
  header { padding: 28px 24px 0; max-width: 1060px; margin: 0 auto; }
  h1 { font-size: 26px; font-weight: 700; letter-spacing: -0.01em; margin: 0; }
  .stamp { color: var(--muted); font-size: 13px; margin-top: 2px; }
  nav { display: flex; gap: 4px; margin-top: 18px; border-bottom: 1px solid var(--border);
        overflow-x: auto; }
  nav button { appearance: none; background: none; border: none; cursor: pointer;
        font: 600 13px/1 system-ui, sans-serif; letter-spacing: 0.04em;
        text-transform: uppercase; color: var(--ink-2); padding: 10px 14px 12px;
        border-bottom: 2px solid transparent; white-space: nowrap; }
  nav button[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--ink); }
  nav button:focus-visible { outline: 2px solid var(--sA); outline-offset: -2px; }
  main { max-width: 1060px; margin: 0 auto; padding: 24px; }
  section[hidden] { display: none; }

  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
           gap: 12px; }
  .tile { background: var(--surface); border: 1px solid var(--border);
          border-radius: 6px; padding: 14px 16px; }
  .tile .k { font-size: 12px; font-weight: 600; letter-spacing: 0.05em;
             text-transform: uppercase; color: var(--muted); }
  .tile .v { font-size: 26px; font-weight: 700; margin-top: 4px; }
  .tile .s { font-size: 12.5px; color: var(--ink-2); margin-top: 2px; }
  .pos { color: var(--good); } .neg { color: var(--bad); }

  .card { background: var(--surface); border: 1px solid var(--border);
          border-radius: 6px; padding: 18px 20px; margin-top: 16px; }
  .card h2 { font-size: 15px; font-weight: 700; margin: 0 0 2px; }
  .card .sub { font-size: 12.5px; color: var(--muted); margin: 0 0 12px; }
  .legend { display: flex; gap: 16px; font-size: 12.5px; color: var(--ink-2);
            margin-bottom: 8px; flex-wrap: wrap; }
  .legend span::before, .legend .lgbtn::before { content: ""; display: inline-block;
            width: 9px; height: 9px; border-radius: 2px; margin-right: 6px; }
  .legend .lgbtn { background: none; border: 1px solid transparent; cursor: pointer;
            font: 12.5px system-ui; color: var(--ink-2); padding: 2px 9px;
            border-radius: 5px; }
  .legend .lgbtn:hover { border-color: var(--border); }
  .legend .lgbtn[aria-pressed="false"] { opacity: 0.35; }
  .legend select { font: 12.5px system-ui; color: var(--ink); background: var(--surface);
            border: 1px solid var(--border); border-radius: 5px; padding: 3px 6px;
            margin-left: auto; }
  .legend .lA::before { background: var(--sA); }
  .legend .lC::before { background: var(--sC); }
  .legend .lE::before { background: var(--sE); }
  .legend .lF::before { background: var(--sF); }
  svg text { font: 11.5px system-ui, sans-serif; fill: var(--muted); }
  svg .end-label { font-weight: 700; font-size: 12px; }
  svg .end-label.tA { fill: var(--sA); } svg .end-label.tC { fill: var(--sC); }
  svg .end-label.tE { fill: var(--sE); }
  svg .end-label.tF { fill: var(--sF); }
  .sA { stroke: var(--sA); } .sC { stroke: var(--sC); } .sE { stroke: var(--sE); }
  .sF { stroke: var(--sF); }
  .fA { fill: var(--sA); } .fC { fill: var(--sC); } .fE { fill: var(--sE); }
  .fF { fill: var(--sF); }
  .gridline { stroke: var(--grid); stroke-width: 1; }
  .zero { stroke: var(--axis); stroke-width: 1.5; }
  .chart-scroll { overflow-x: auto; }

  table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
  th { text-align: left; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase;
       color: var(--muted); font-weight: 600; padding: 6px 12px 6px 0; }
  td { padding: 7px 12px 7px 0; border-top: 1px solid var(--grid); font-size: 14px; }
  td.num, th.num { text-align: right; }
  .rule-dot { display: inline-block; width: 9px; height: 9px; border-radius: 2px;
              margin-right: 8px; vertical-align: baseline; }

  .slots { display: flex; gap: 6px; flex-wrap: wrap; }
  .slot { width: 44px; height: 44px; border-radius: 6px; border: 1px dashed var(--axis);
          display: flex; align-items: center; justify-content: center;
          font-size: 11px; color: var(--muted); flex-direction: column; gap: 1px; }
  .slot.done { border-style: solid; background: var(--chip); color: var(--ink-2); }
  .slot .n { font-weight: 700; font-size: 13px; color: var(--ink); }

  .empty { border: 1px dashed var(--axis); border-radius: 6px; padding: 28px 24px;
           text-align: center; color: var(--ink-2); margin-top: 16px; }
  .empty strong { color: var(--ink); }

  #tooltip { position: fixed; pointer-events: none; background: var(--surface);
             border: 1px solid var(--border); border-radius: 5px; padding: 8px 10px;
             font-size: 12.5px; box-shadow: 0 4px 14px rgba(0,0,0,0.18);
             display: none; z-index: 10; max-width: 260px; }
  #tooltip .t { font-weight: 700; margin-bottom: 3px; }
  #tooltip .row { display: flex; justify-content: space-between; gap: 14px;
                  font-variant-numeric: tabular-nums; }

  .doc { max-width: 72ch; }
  .doc h1 { font-size: 24px; margin: 0 0 4px; }
  .doc h2 { font-size: 19px; margin: 32px 0 8px; padding-top: 18px;
            border-top: 1px solid var(--grid); }
  .doc h3 { font-size: 15.5px; margin: 22px 0 6px; }
  .doc p, .doc li { color: var(--ink-2); }
  .doc strong { color: var(--ink); }
  .doc a { color: var(--sA); }
  .doc code { background: var(--chip); border-radius: 3px; padding: 1px 5px;
              font: 13px ui-monospace, "SF Mono", Menlo, monospace; }
  .doc pre { background: var(--chip); border-radius: 6px; padding: 12px 14px;
             overflow-x: auto; }
  .doc pre code { background: none; padding: 0; }
  .doc table { display: block; overflow-x: auto; margin: 12px 0; width: fit-content;
               max-width: 100%; }
  .doc th, .doc td { text-transform: none; letter-spacing: 0; padding: 6px 14px 6px 0; }
  footer { max-width: 1060px; margin: 0 auto; padding: 8px 24px 32px;
           color: var(--muted); font-size: 12.5px; }
</style>

<header>
  <h1>Octagon Ledger</h1>
  <div class="stamp">Model vs market, graded weekly &middot; updated __UPDATED__</div>
  <nav id="tabs" role="tablist">
    <button role="tab" data-tab="performance" aria-selected="true">Performance</button>
    <button role="tab" data-tab="trial" aria-selected="false">Experiments</button>
    <button role="tab" data-tab="history" aria-selected="false">History</button>
    <button role="tab" data-tab="methodology" aria-selected="false">Methodology</button>
    <button role="tab" data-tab="dictionary" aria-selected="false">Data dictionary</button>
    <button role="tab" data-tab="faq" aria-selected="false">FAQ</button>
  </nav>
</header>

<main>
  <section id="tab-performance" role="tabpanel">
    <div class="tiles" id="perf-tiles"></div>
    <div class="card" id="perf-chart" style="margin-top:16px"></div>
    <div class="card" id="upcoming-card"></div>
    <div class="card">
      <h2>Past events</h2>
      <p class="sub">Click an event for every fight and what rule A staked on it.</p>
      <div id="events-list"></div>
    </div>
  </section>

  <section id="tab-trial" role="tabpanel" hidden>
    <!-- rule/trial explainer lives in Methodology 13.1 (moved 23 Aug 2026) -->

    <div class="tiles" id="tiles"></div>
    <div id="charts"></div>

    <div class="card">
      <h2>Rule comparison &middot; live record</h2>
      <p class="sub">Rule A is staked with real money; C (vig floor), E (shrunk staking) and F (fitted blend) are shadow-logged on identical cards. Net is the real $50-bankroll-replay number the promotion decision (below) is made on.</p>
      <div class="chart-scroll"><table id="rule-table"></table></div>
    </div>

    <div class="card">
      <h2>Backtest reference &middot; why the shadows are being trialled</h2>
      <p class="sub">5,786 historical fights at closing odds (C/E: entry 9; F: entry 10, whole-history replay at the frozen &lambda;). H2 = the more recent half. All ROIs are upper bounds.</p>
      <div class="chart-scroll"><table>
        <tr><th>Rule</th><th class="num">Bets</th><th class="num">Hit rate</th><th class="num">Flat ROI</th><th class="num">Kelly ROI</th><th class="num">H2 flat</th><th class="num">H2 kelly</th></tr>
        <tr><td><span class="rule-dot fA"></span>A &mdash; kelly value (staked)</td><td class="num">4,536</td><td class="num">55.9%</td><td class="num">+6.1%</td><td class="num">+14.0%</td><td class="num">+0.9%</td><td class="num">+4.8%</td></tr>
        <tr><td><span class="rule-dot fC"></span>C &mdash; vig floor (shadow)</td><td class="num">3,288</td><td class="num">54.6%</td><td class="num">+9.4%</td><td class="num">+16.0%</td><td class="num">+8.0%</td><td class="num">+12.9%</td></tr>
        <tr><td><span class="rule-dot fE"></span>E &mdash; shrunk staking (shadow)</td><td class="num">3,340</td><td class="num">54.6%</td><td class="num">+9.2%</td><td class="num">+27.9%</td><td class="num">+7.4%</td><td class="num">+23.8%</td></tr>
        <tr><td><span class="rule-dot fF"></span>F &mdash; fitted blend (shadow)</td><td class="num">4,110</td><td class="num">55.7%</td><td class="num">+7.3%</td><td class="num">+18.3%</td><td class="num">+2.9%</td><td class="num">+7.5%</td></tr>
      </table></div>
    </div>
  </section>

  <section id="tab-history" role="tabpanel" hidden>
    <div class="tiles" id="hist-tiles"></div>
    <div id="hist-body"></div>
  </section>

  <section id="tab-methodology" role="tabpanel" hidden>
    <p style="max-width:72ch;margin:0 0 4px">
      <input id="methodology-search" type="search" placeholder="Search the methodology — e.g. elo, mirroring, kelly"
        style="width:100%;padding:9px 12px;font:14px system-ui;color:var(--ink);background:var(--surface);border:1px solid var(--border);border-radius:6px">
      <span id="methodology-count" class="stamp"></span>
    </p>
    <article class="doc">__METHODOLOGY__</article>
  </section>
  <section id="tab-dictionary" role="tabpanel" hidden>
    <p style="max-width:72ch;margin:0 0 4px">
      <input id="dict-search" type="search" placeholder="Search columns and definitions — e.g. elo, avg_r_kd, layoff"
        style="width:100%;padding:9px 12px;font:14px system-ui;color:var(--ink);background:var(--surface);border:1px solid var(--border);border-radius:6px">
      <span id="dict-count" class="stamp"></span>
    </p>
    <article class="doc">__DICTIONARY__</article>
  </section>
  <section id="tab-faq" role="tabpanel" hidden>
    <p style="max-width:72ch;margin:0 0 4px">
      <input id="faq-search" type="search" placeholder="Search the FAQ — e.g. kelly, retrain, shadow"
        style="width:100%;padding:9px 12px;font:14px system-ui;color:var(--ink);background:var(--surface);border:1px solid var(--border);border-radius:6px">
      <span id="faq-count" class="stamp"></span>
    </p>
    <article class="doc">__FAQ__</article>
  </section>
</main>
<footer>Rebuilt by the Monday scoring Routine from <code>ledger.md</code> on the weekly-predictions-log branch.</footer>
<div id="tooltip"></div>

<script>
const DATA = __DATA__;
const RULES = ["A", "C", "E", "F"];
const RULE_NAME = {A: "A · kelly value", C: "C · vig floor", E: "E · shrunk", F: "F · fitted blend"};
const fmt$ = v => (v < 0 ? "−$" : "$") + Math.abs(v).toFixed(2);
const sign$ = v => (v >= 0 ? "+$" : "−$") + Math.abs(v).toFixed(2);
const cls = v => v >= 0 ? "pos" : "neg";
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// -- tabs ------------------------------------------------------------------
const tabs = document.getElementById("tabs");
function showTab(name) {
  for (const b of tabs.querySelectorAll("button"))
    b.setAttribute("aria-selected", String(b.dataset.tab === name));
  for (const s of document.querySelectorAll("main > section"))
    s.hidden = s.id !== "tab-" + name;
}
tabs.addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  showTab(b.dataset.tab); history.replaceState(null, "", "#" + b.dataset.tab);
});
function tabFromHash() {
  const t = location.hash.slice(1);
  if (t && document.getElementById("tab-" + t)) showTab(t);
}
window.addEventListener("hashchange", tabFromHash);
tabFromHash();

// -- tooltip ---------------------------------------------------------------
// Hover shows it transiently; clicking a data point PINS it (stays up so the
// numbers can be read without holding the pointer still). While pinned,
// hover/leave are ignored; any click that isn't on another data point unpins.
const tip = document.getElementById("tooltip");
let tipPinned = false;
function tipShow(html, x, y, pin) {
  if (tipPinned && !pin) return;
  tipPinned = !!pin;
  tip.innerHTML = html + (pin
    ? `<div class="row" style="color:var(--muted);margin-top:4px">click anywhere to dismiss</div>` : "");
  tip.style.display = "block";
  const w = tip.offsetWidth, vw = window.innerWidth;
  tip.style.left = Math.min(x + 14, vw - w - 8) + "px";
  tip.style.top = (y + 14) + "px";
}
function tipHide(force) {
  if (tipPinned && !force) return;
  tip.style.display = "none";
}
document.addEventListener("click", () => {
  // runs at bubble end; chart click handlers that pin call stopPropagation()
  if (tipPinned) { tipPinned = false; tipHide(true); }
});

// -- summary tiles ---------------------------------------------------------
const ev = DATA.events, tot = DATA.totals;
const n = ev.length, A = tot.A;
const tiles = document.getElementById("tiles");
function tile(k, v, s, vClass) {
  tiles.insertAdjacentHTML("beforeend",
    `<div class="tile"><div class="k">${k}</div><div class="v ${vClass || ""}">${v}</div><div class="s">${s}</div></div>`);
}
if (n) {
  const lead = RULES.map(r => [r, tot[r].net]).sort((a, b) => b[1] - a[1])[0];
  tile("Trial progress", n + " / 10", "leader so far: rule " + lead[0] + " (" + sign$(lead[1]) + ")");
} else {
  tile("Trial progress", "0 / 10", "first grading pending");
}

// -- charts ----------------------------------------------------------------
const shortName = t => esc(t.replace(/^UFC (Fight Night|on \w+)[:\s]*/i, "").split(":")[0].trim());
const EVENT_STATS = __EVENT_STATS__;

// One consolidated chart engine, reused for the Experiments tab (all rules)
// and the Performance tab (rule A only): a metric selector switches what's
// plotted -- net return, hit rate, bet rate, avg market win% -- as running
// (cumulative-to-date) values, one axis at a time (never dual-axis). Marker
// SIZE always reflects that event's real net $ swing regardless of which
// metric is on screen, so the "how big was this event" cue survives every
// view. x = events, with a $0/undefined start point so n=1 still draws.
const METRIC_DEFS = {
  net:     {label: "Net return ($50 staked)",
            axisFmt: v => (v < 0 ? "−$" : "$") + Math.abs(Math.round(v)),
            endFmt: v => sign$(v)},
  flatnet: {label: "Net return ($1 flat/bet)",
            axisFmt: v => (v < 0 ? "−$" : "$") + Math.abs(Math.round(v)),
            endFmt: v => sign$(v)},
  hit:     {label: "Hit rate (%)", axisFmt: v => Math.round(v) + "%",
            endFmt: v => v.toFixed(0) + "%"},
  betrate: {label: "Bet rate (%)", axisFmt: v => Math.round(v) + "%",
            endFmt: v => v.toFixed(0) + "%"},
  market:  {label: "Avg market win (%)", axisFmt: v => Math.round(v) + "%",
            endFmt: v => v.toFixed(0) + "%"},
};
function buildSeries(rules) {
  const s = {}; for (const m of Object.keys(METRIC_DEFS)) s[m] = {};
  for (const r of rules) {
    let netAcc = 0, flatAcc = 0, won = 0, placed = 0, offeredAcc = 0, implSum = 0, bets = 0;
    s.net[r] = [0]; s.flatnet[r] = [0]; s.hit[r] = [0]; s.betrate[r] = [0]; s.market[r] = [0];
    ev.forEach(e => {
      const row = e.rules[r];
      const st = EVENT_STATS[e.date + "|" + e.event];
      const ruleSt = st && st.rules ? st.rules[r] : null;
      netAcc += row ? row.net : 0;
      flatAcc += row ? row.flat_net : 0;
      won += row ? row.won : 0;
      placed += row ? row.placed : 0;
      offeredAcc += st ? st.offered : 0;
      if (ruleSt) { implSum += ruleSt.implied_sum; bets += ruleSt.bets; }
      s.net[r].push(netAcc);
      s.flatnet[r].push(flatAcc);
      s.hit[r].push(placed ? 100 * won / placed : 0);
      s.betrate[r].push(offeredAcc ? 100 * placed / offeredAcc : 0);
      s.market[r].push(bets ? implSum / bets : 0);
    });
  }
  return s;
}

function drawMetricChart(svg, rules, metricKey, series) {
  const def = METRIC_DEFS[metricKey];
  const W = 940, H = 300, L = 46, R = 76, T = 16, B = 40, ticks = 4;
  const cum = {}; rules.forEach(r => cum[r] = series[metricKey][r]);
  const allY = rules.flatMap(r => cum[r]);
  const yMax = Math.max(metricKey === "net" ? 5 : metricKey === "flatnet" ? 1 : 10, ...allY), yMin = Math.min(0, ...allY);
  const pad = (yMax - yMin) * 0.08 || 1;
  const ySc = v => T + (yMax + pad - v) / (yMax + pad - yMin + pad) * (H - T - B);
  const xSc = i => L + i / Math.max(1, n) * (W - L - R);
  const maxAbsNet = Math.max(1, ...ev.flatMap(e => rules.map(r => Math.abs(e.rules[r] ? e.rules[r].net : 0))));
  const rScale = v => 3.5 + (Math.abs(v) / maxAbsNet) * 6.5;  // marker radius 3.5-10px

  let g = "";
  for (let i = 0; i <= ticks; i++) {
    const v = yMin + (yMax - yMin) * i / ticks, y = ySc(v);
    g += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/>
          <text x="${L - 8}" y="${y + 4}" text-anchor="end">${def.axisFmt(v)}</text>`;
  }
  g += `<line class="zero" x1="${L}" x2="${W - R}" y1="${ySc(0)}" y2="${ySc(0)}"/>`;
  g += `<text x="${xSc(0)}" y="${H - B + 18}" text-anchor="middle">start</text>`;
  ev.forEach((e, i) => g += `<text x="${xSc(i + 1)}" y="${H - B + 18}" text-anchor="middle">${shortName(e.event)}</text>`);
  for (const r of rules) {
    const pts = cum[r].map((v, i) => xSc(i).toFixed(1) + "," + ySc(v).toFixed(1)).join(" ");
    g += `<polyline class="s${r}" points="${pts}" fill="none" stroke-width="2" stroke-linejoin="round"/>`;
    cum[r].forEach((v, i) => {
      if (i === 0) return;
      const row = ev[i - 1].rules[r], rad = row ? rScale(row.net) : 3.5;
      g += `<circle class="f${r} pt" data-r="${r}" data-i="${i - 1}" cx="${xSc(i)}" cy="${ySc(v)}" r="${rad.toFixed(1)}" stroke="var(--surface)" stroke-width="2"/>`;
    });
  }
  const ends = rules.map(r => ({r, y: ySc(cum[r][n])})).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++)
    if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  for (const e2 of ends)
    g += `<text class="end-label t${e2.r}" x="${W - R + 8}" y="${e2.y + 4}">${e2.r} ${def.endFmt(cum[e2.r][n])}</text>`;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = g;
}

const METRIC_SUB = {
  flatnet: () => `Cumulative net profit per rule at a flat $1 per bet, not the actual $ staked — stake size differs by rule (some concentrate into one bet, some spread out), so comparing on real dollars exaggerates whichever rule happens to concentrate more. Marker size is that event's real $ swing (see the tooltip for actual staked/returned).`,
  net: (n1) => `Cumulative net profit per rule at the real $50-bankroll stakes — the number the promotion decision runs on; marker size is that event's net swing. ${n1 > 1 ? "Every rule replays the same $50 bankroll each event." : ""}`,
  hit: () => "Running hit rate to date (cumulative wins &divide; cumulative bets placed) per rule.",
  betrate: () => "Running bet rate to date (cumulative bets placed &divide; cumulative fights offered) per rule — how often each rule finds value.",
  market: () => "Running average odds-implied win probability of each rule's own bets to date — higher means shorter-priced, safer picks.",
};
let chartSeq = 0;
function initReturnChart(container, rules, title, defaultMetric, omit) {
  defaultMetric = defaultMetric || "net";
  if (!n) {
    container.insertAdjacentHTML("beforeend",
      `<h2>${title}</h2><div class="empty" style="margin-top:8px">
       <strong>No events scored yet.</strong><br>
       Fills in after the Monday Routine grades the first card.</div>`);
    return;
  }
  const uid = "rc" + (chartSeq++);
  const series = buildSeries(rules);
  const legend = rules.length > 1
    ? `<div class="legend">${rules.map(r => `<span class="l${r}">${r} &middot; ${r === "A" ? "staked" : "shadow"}</span>`).join("")}</div>`
    : "";
  const options = Object.entries(METRIC_DEFS)
    .filter(([k]) => !(omit || []).includes(k))
    .map(([k, d]) => `<option value="${k}"${k === defaultMetric ? " selected" : ""}>${d.label}</option>`).join("");
  container.insertAdjacentHTML("beforeend", `
    <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px">
      <h2 style="margin:0">${title}</h2>
      <select id="${uid}-metric" style="font:12.5px system-ui;color:var(--ink);background:var(--surface);border:1px solid var(--border);border-radius:5px;padding:5px 8px">${options}</select>
    </div>
    <p class="sub" id="${uid}-sub"></p>${legend}
    <div class="chart-scroll"><svg id="${uid}-svg" viewBox="0 0 940 300" style="min-width:640px;width:100%"></svg></div>`);
  const sel = document.getElementById(uid + "-metric");
  const subEl = document.getElementById(uid + "-sub");
  const svgEl = document.getElementById(uid + "-svg");
  function redraw() {
    subEl.innerHTML = METRIC_SUB[sel.value] ? METRIC_SUB[sel.value](n) : "";
    drawMetricChart(svgEl, rules, sel.value, series);
  }
  sel.addEventListener("change", redraw);
  redraw();

  function ptHtml(t) {
    const i = +t.dataset.i, r = t.dataset.r, row = ev[i].rules[r];
    if (!row) return null;
    const st = EVENT_STATS[ev[i].date + "|" + ev[i].event];
    const ruleSt = st && st.rules ? st.rules[r] : null;
    const hit = row.placed ? Math.round(100 * row.won / row.placed) + "% (" + row.won + "/" + row.placed + ")" : "—";
    const betRate = (st && st.offered) ? Math.round(100 * row.placed / st.offered) + "% (" + row.placed + "/" + st.offered + ")" : "—";
    const mktAvg = (ruleSt && ruleSt.bets) ? (ruleSt.implied_sum / ruleSt.bets).toFixed(1) + "%" : "—";
    return `<div class="t">${esc(ev[i].event)}</div>
      <div class="row"><span>${RULE_NAME[r]}</span><span class="${cls(row.net)}">${sign$(row.net)} real / ${sign$(row.flat_net)} flat</span></div>
      <div class="row"><span>staked → returned</span><span>${fmt$(row.staked)} → ${fmt$(row.returned)}</span></div>
      <div class="row"><span>hit rate</span><span>${hit}${row.void ? ", " + row.void + " void" : ""}</span></div>
      <div class="row"><span>bet rate</span><span>${betRate}</span></div>
      <div class="row"><span>avg market win</span><span>${mktAvg}</span></div>`;
  }
  container.addEventListener("pointermove", e => {
    const t = e.target.closest(".pt");
    if (!t) return tipHide();
    const html = ptHtml(t);
    html ? tipShow(html, e.clientX, e.clientY) : tipHide();
  });
  container.addEventListener("click", e => {
    const t = e.target.closest(".pt");
    if (!t) return;
    const html = ptHtml(t);
    if (html) { tipShow(html, e.clientX, e.clientY, true); e.stopPropagation(); }
  });
  container.addEventListener("pointerleave", () => tipHide());
}

const expChartCard = document.createElement("div");
expChartCard.className = "card";
document.getElementById("charts").appendChild(expChartCard);
// flat-$1 dropped from this chart at Michael's request (23 Aug) -- the
// flat comparison lives in the Rule comparison table's own column now
initReturnChart(expChartCard, RULES, "Return &amp; performance over time", "net", ["flatnet"]);

// -- rule table ------------------------------------------------------------
// Indicative retro-CLV for the first three trial events (Sep 2026 one-off
// analysis: Best Fight Odds US-book closing medians, NOT the same-book
// Sportsbet basis the live snapshots use). Shown only while a rule has no
// live Avg CLV yet; the ledger-driven value replaces it as snapshots accrue.
const RETRO_CLV = { A: 2.5, C: 5.3, E: 5.3, F: 2.6 };
const rt = document.getElementById("rule-table");
rt.innerHTML = `<tr><th>Rule</th><th class="num">Staked</th>
  <th class="num">Returned</th><th class="num">Net</th><th class="num">ROI</th>
  <th class="num">Hit rate</th><th class="num">Avg CLV</th><th class="num">Cards ahead of A</th></tr>` +
  RULES.map(r => {
    const t = tot[r];
    return `<tr><td><span class="rule-dot f${r}"></span>${RULE_NAME[r]}${r === "A" ? " (staked)" : " (shadow)"}</td>
      <td class="num">${n ? fmt$(t.staked) : "—"}</td>
      <td class="num">${n ? fmt$(t.returned) : "—"}</td>
      <td class="num ${n ? cls(t.net) : ""}">${n ? sign$(t.net) : "—"}</td>
      <td class="num ${n ? cls(t.net) : ""}">${t.roi === null ? "—" : (t.roi >= 0 ? "+" : "") + t.roi + "%"}</td>
      <td class="num">${t.hit === null ? "—" : t.hit + "% (" + t.won + "/" + t.placed + ")"}</td>
      <td class="num ${t.clv === null ? "" : cls(t.clv)}" title="avg closing-line value: taken price vs the pre-fight closing snapshot; positive = beat the close">${t.clv === null
        ? (RETRO_CLV[r] !== undefined ? `<span style="color:var(--muted)">+${RETRO_CLV[r]}%*</span>` : "—")
        : (t.clv >= 0 ? "+" : "") + t.clv + "%"}</td>
      <td class="num">${r === "A" ? "—" : n ? t.ahead + " / " + n : "—"}</td></tr>`;
  }).join("");
if (RULES.some(r => tot[r].clv === null && RETRO_CLV[r] !== undefined))
  rt.insertAdjacentHTML("afterend",
    `<p class="sub" style="margin-top:6px">* indicative retro estimate for the first three trial events
     (Best Fight Odds US-book closing medians — not the same-book Sportsbet basis the live snapshots use);
     replaced by ledger snapshot values as they accrue from Sep 2026.</p>`);

// -- Performance tab: P/L so far, upcoming allocator, past events ----------
const NEXT = __NEXT__;
const EVENT_DETAIL = __EVENT_DETAIL__;

// P/L so far (rule A -- the real money)
const perfTiles = document.getElementById("perf-tiles");
if (n) {
  perfTiles.insertAdjacentHTML("beforeend",
    `<div class="tile"><div class="k">Profit / loss so far</div>
     <div class="v ${cls(A.net)}">${sign$(A.net)}</div>
     <div class="s">${fmt$(A.staked)} staked &rarr; ${fmt$(A.returned)} back across ${n} event${n === 1 ? "" : "s"}</div></div>
    <div class="tile"><div class="k">Rule A ROI</div>
     <div class="v ${cls(A.roi)}">${(A.roi >= 0 ? "+" : "") + A.roi}%</div>
     <div class="s">on money actually staked</div></div>`);
} else {
  perfTiles.insertAdjacentHTML("beforeend",
    `<div class="tile"><div class="k">Profit / loss so far</div>
     <div class="v">&mdash;</div><div class="s">no events scored yet</div></div>
    <div class="tile"><div class="k">Rule A ROI</div>
     <div class="v">&mdash;</div><div class="s">no events scored yet</div></div>`);
}
initReturnChart(document.getElementById("perf-chart"), ["A"], "Rule A over time");

// upcoming card: bankroll allocator
const upcomingEl = document.getElementById("upcoming-card");
if (!NEXT || NEXT.decided) {
  upcomingEl.innerHTML = NEXT
    ? `<h2>Upcoming card</h2><p class="sub" style="margin-bottom:0"><strong>${esc(NEXT.event)}</strong>
        has already happened — see it under Past events below, or the Experiments
        tab for the graded rule comparison. The next upcoming card replaces this
        once Friday's card-day job runs.</p>`
    : `<h2>Upcoming card</h2><p class="sub" style="margin-bottom:0">No upcoming card logged yet —
        check back after 9&nbsp;AM AEST Friday.</p>`;
} else {
  const valueFights = NEXT.fights.map((f, i) => ({...f, i})).filter(f => f.kelly > 0);
  upcomingEl.innerHTML = `
    <h2>${esc(NEXT.event)}</h2>
    <p class="sub">Enter a total bankroll for this card; it's split across the
      ${valueFights.length} of ${NEXT.fights.length} fights the model finds value
      in, proportional to Kelly fraction — the same split
      <code>send_weekly_predictions.py</code> uses. Predicted without knowing the
      event's host country, so confidence can differ slightly from the original
      card-day run.</p>
    <label style="font-size:13.5px;color:var(--ink-2)">Bankroll $
      <input id="bankroll-input" type="number" min="0" step="1" value="${NEXT.bankroll}"
        style="width:90px;font:14px system-ui;color:var(--ink);background:var(--surface);border:1px solid var(--border);border-radius:5px;padding:6px 8px;margin-left:6px"></label>
    <div class="chart-scroll"><table id="alloc-table">
      <tr><th>Fight</th><th>Model pick</th><th class="num">Odds</th><th class="num">Allocated</th><th class="num">Returns if wins</th></tr>
      ${NEXT.fights.map((f, i) => `<tr data-i="${i}">
        <td>${esc(f.f1)} <span style="color:var(--muted)">vs</span> ${esc(f.f2)}</td>
        <td>${f.bet_on ? esc(f.bet_on) : '<span style="color:var(--muted)">no value</span>'}</td>
        <td class="num">${f.bet_on ? f.bet_odds.toFixed(2) : "—"}</td>
        <td class="num alloc-out">$0</td><td class="num ret-out">—</td></tr>`).join("")}
      <tr style="font-weight:700"><td colspan="3">Total if every placed bet wins</td>
        <td class="num alloc-total-out">$0</td><td class="num ret-total-out">—</td></tr>
    </table></div>
    <p class="sub" style="margin:8px 0 0">That total is a ceiling, not an expectation &mdash; each fight is an
      independent bet, so realistically some win and some lose. It's what you'd collect only in the (unlikely)
      case every placed bet comes in.</p>`;
  const bInput = document.getElementById("bankroll-input");
  const allocRows = [...document.querySelectorAll("#alloc-table tr[data-i]")];
  const allocTotalOut = document.querySelector(".alloc-total-out");
  const retTotalOut = document.querySelector(".ret-total-out");
  function recompute() {
    const total = parseFloat(bInput.value) || 0;
    let stakes = {};
    if (valueFights.length && total > 0) {
      const totalK = valueFights.reduce((s, f) => s + f.kelly, 0);
      let sum = 0;
      for (const f of valueFights) {
        const amt = Math.round(total * f.kelly / totalK);
        stakes[f.i] = amt; sum += amt;
      }
      const top = valueFights.reduce((a, b) => b.kelly > a.kelly ? b : a);
      stakes[top.i] += total - sum;  // rounding remainder to the biggest edge
    }
    let stakedSum = 0, returnSum = 0;
    allocRows.forEach(row => {
      const i = +row.dataset.i, f = NEXT.fights[i], amt = stakes[i] || 0;
      row.querySelector(".alloc-out").textContent = amt ? fmt$(amt) : "$0";
      row.querySelector(".ret-out").textContent = amt ? fmt$(amt * f.bet_odds) : "—";
      stakedSum += amt;
      if (amt) returnSum += amt * f.bet_odds;
    });
    allocTotalOut.textContent = fmt$(stakedSum);
    retTotalOut.textContent = returnSum ? fmt$(returnSum) : "—";
  }
  bInput.addEventListener("input", recompute);
  recompute();
}

// past events: view-only, one collapsible <details> per event
const eventsListEl = document.getElementById("events-list");
if (!n) {
  eventsListEl.innerHTML = `<div class="empty" style="margin-top:0">No events scored yet.</div>`;
} else {
  eventsListEl.innerHTML = ev.slice().reverse().map(e => {
    const a = e.rules.A;
    const rows = EVENT_DETAIL[e.date + "|" + e.event] || [];
    const body = rows.length
      ? `<div class="chart-scroll" style="margin-top:10px"><table>
          <tr><th>Fight</th><th>Model pick</th><th class="num">Odds</th><th class="num">Rule A stake</th><th>Shadow stakes (C / E / F)</th></tr>
          ${rows.map(f => `<tr><td>${esc(f.f1)} <span style="color:var(--muted)">vs</span> ${esc(f.f2)}</td>
            <td>${esc(f.pick)} (${esc(f.confidence)})</td>
            <td class="num">${f.bet_on ? f.bet_odds.toFixed(2) : "—"}</td>
            <td class="num">${f.stake ? fmt$(f.stake) : "$0"}</td>
            <td style="color:var(--muted);font-size:12px">${f.shadow && f.shadow !== "-" ? esc(f.shadow) : "—"}</td></tr>`).join("")}
        </table></div>`
      : `<p class="sub" style="margin:10px 0 0">Per-fight detail unavailable for this event.</p>`;
    return `<details style="margin-top:10px;border:1px solid var(--border);border-radius:6px;padding:12px 16px">
      <summary style="cursor:pointer;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:14px">
        <span><strong>${esc(e.event)}</strong> <span style="color:var(--muted)">&middot; ${e.date}</span></span>
        <span>${a ? fmt$(a.staked) + " &rarr; " + fmt$(a.returned) + " &middot; " : ""}<span class="${a ? cls(a.net) : ""}">${a ? sign$(a.net) : "—"}</span></span>
      </summary>
      ${body}
    </details>`;
  }).join("");
}

// -- history: the full what-if replay --------------------------------------
const HIST = __HIST__;
const htiles = document.getElementById("hist-tiles");
const hbody = document.getElementById("hist-body");
function htile(k, v, s, vClass) {
  htiles.insertAdjacentHTML("beforeend",
    `<div class="tile"><div class="k">${k}</div><div class="v ${vClass || ""}">${v}</div><div class="s">${s}</div></div>`);
}
if (!HIST) {
  hbody.insertAdjacentHTML("beforeend",
    `<div class="empty" style="margin-top:0"><strong>Replay data not in this build.</strong><br>
     It needs odds_train.csv (rebuilt per container by scripts/fetch_training_odds.py —
     the odds source is unlicensed upstream, so it is never committed) next to
     ensemble.joblib. The next scheduled rebuild restores this tab.</div>`);
} else {
  // one year filter drives the whole tab: tiles, chart, summary, bet table
  const allMonths = [...new Set(RULES.flatMap(r => HIST.bets[r].map(b => b[0].slice(0, 7))))].sort();
  const histYears = [...new Set(allMonths.map(m => m.slice(0, 4)))];
  htiles.insertAdjacentHTML("beforebegin",
    `<div class="legend" style="margin:0 0 12px;align-items:center">
       <span style="font-weight:600;color:var(--ink)">Historical replay</span>
       <label style="margin-left:auto;color:var(--muted);font-size:12.5px">From
         <select id="hist-y1" style="margin-left:4px">${histYears.map(y => `<option>${y}</option>`).join("")}</select></label>
       <label style="color:var(--muted);font-size:12.5px">To
         <select id="hist-y2" style="margin-left:4px">${histYears.map((y, i) => `<option${i === histYears.length - 1 ? " selected" : ""}>${y}</option>`).join("")}</select></label>
     </div>`);
  const y1Sel = document.getElementById("hist-y1"), y2Sel = document.getElementById("hist-y2");
  const yrRange = () => {
    const a = y1Sel.value, b = y2Sel.value;
    return a <= b ? [a, b] : [b, a];  // swap if picked backwards
  };
  const inRange = (d, R) => d.slice(0, 4) >= R[0] && d.slice(0, 4) <= R[1];
  const fightsIn = R => histYears.filter(y => y >= R[0] && y <= R[1])
    .reduce((n, y) => n + ((HIST.fights_by_year || {})[y] || 0), 0);

  // metrics per rule within the selected year: flat = $1/bet; kelly = stake-weighted
  function metrics(r, R) {
    let flat = 0, kst = 0, kpr = 0, won = 0, n = 0, imp = 0;
    for (const row of HIST.bets[r]) {
      if (!inRange(row[0], R)) continue;
      const [odds, k, w] = row.slice(-3);
      n++; flat += w ? odds - 1 : -1;
      kst += k; kpr += w ? k * (odds - 1) : -k; won += w;
      imp += 1 / odds;
    }
    return {n, flat, kellyPL: kpr, kellyStaked: kst,
            hit: n ? 100 * won / n : 0, avgImp: n ? 100 * imp / n : 0,
            flatROI: n ? 100 * flat / n : 0, kellyROI: kst ? 100 * kpr / kst : 0};
  }

  function renderTiles(R) {
    htiles.innerHTML = "";
    const A = metrics("A", R);
    const span = R[0] === R[1] ? R[0] : R[0] + "–" + R[1];
    htile("Fights with odds", fightsIn(R).toLocaleString(), span);
    htile("Rule A bets", A.n.toLocaleString(), A.n ? A.hit.toFixed(1) + "% hit rate" : "—");
    htile("Flat $1 per bet", A.n ? sign$(A.flat) : "—", A.n ? A.flatROI.toFixed(1) + "% ROI on " + A.n.toLocaleString() + " × $1" : "—", A.n ? cls(A.flat) : "");
    htile("Kelly ROI", A.n ? (A.kellyROI >= 0 ? "+" : "") + A.kellyROI.toFixed(1) + "%" : "—", "stake-weighted, uncompounded", A.n ? cls(A.kellyROI) : "");
  }

  // per-month series (net $1/bet, hit rate, bet rate, avg market win%) by
  // month; rules + metric toggle here, year comes from the tab filter
  const W = 940, H = 320, L = 52, R = 86, T = 16, B = 34;
  const MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const histMetricSub = {
    net: () => "Cumulative profit with each bet staking its kelly fraction of a fixed $1 (non-compounding) — same $1 bankroll-unit as the flat view, but kelly risks only the kelly-size share of it (capped 25%), weighting confident bets more. Same pooled out-of-fold fights matched to closing odds; upper bounds apply.",
    flatnet: () => "Cumulative profit, $1 flat per bet, each rule applied to the same pooled out-of-fold fights (the model never trained on the fight it predicts) matched to closing odds. Upper bounds: closing-odds conditioning, no line movement.",
    hit: () => "Running hit rate to date (cumulative wins &divide; cumulative bets) per rule, by month.",
    betrate: () => "Running bet rate to date (cumulative bets &divide; cumulative fights with odds that month) per rule — how often each rule finds value.",
    market: () => "Running average odds-implied win probability of each rule's own bets to date — higher means shorter-priced, safer picks.",
  };
  // History has no $50-bankroll-per-event replay (backtest is per-bet), so
  // its "staked" net is kelly-weighted — label the two net options accordingly.
  const histMetricLabel = k => k === "net" ? "Net return (kelly-staked)" : METRIC_DEFS[k].label;
  hbody.insertAdjacentHTML("beforeend", `<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px">
      <h2 style="margin:0">The whole-history replay</h2>
      <select id="hist-metric" style="font:12.5px system-ui;color:var(--ink);background:var(--surface);border:1px solid var(--border);border-radius:5px;padding:5px 8px">${Object.keys(METRIC_DEFS).map(k => `<option value="${k}"${k === "flatnet" ? " selected" : ""}>${histMetricLabel(k)}</option>`).join("")}</select>
    </div>
    <p class="sub" id="hist-sub"></p>
    <div class="legend" id="hist-controls">
      <button class="lgbtn lA" data-r="A" aria-pressed="true">A &middot; kelly value</button>
      <button class="lgbtn lC" data-r="C" aria-pressed="true">C &middot; vig floor</button>
      <button class="lgbtn lE" data-r="E" aria-pressed="true">E &middot; shrunk</button>
      <button class="lgbtn lF" data-r="F" aria-pressed="true">F &middot; fitted blend</button>
    </div>
    <div class="chart-scroll"><svg id="histchart" viewBox="0 0 ${W} ${H}" style="min-width:640px;width:100%"></svg></div>
  </div>`);
  const hsvg = document.getElementById("histchart");
  const hMetricSel = document.getElementById("hist-metric");
  const hSubEl = document.getElementById("hist-sub");
  let hMonths = [], hSeries = {}, hCum = {}, hActive = [...RULES];
  let hxS = i => i, hyS = v => v;

  // full per-month series for every metric at once (cheap at this data size)
  function computeHistSeries(months) {
    const mi = new Map(months.map((m, i) => [m, i]));
    const out = {};
    for (const r of hActive) {
      const netPer = new Array(months.length).fill(0), flatPer = new Array(months.length).fill(0);
      const wonPer = new Array(months.length).fill(0);
      const betsPer = new Array(months.length).fill(0), implPer = new Array(months.length).fill(0);
      for (const row of HIST.bets[r]) {
        const key = row[0].slice(0, 7);
        if (!mi.has(key)) continue;
        const [odds, k, w] = row.slice(-3), idx = mi.get(key);
        // net: kelly fraction of a fixed $1 per bet (non-compounding, same
        // convention as the per-bet table); flatnet: the whole $1 every bet
        netPer[idx] += k * (w ? odds - 1 : -1);
        flatPer[idx] += w ? odds - 1 : -1;
        wonPer[idx] += w ? 1 : 0;
        betsPer[idx] += 1;
        implPer[idx] += 100 / odds;
      }
      let netAcc = 0, flatAcc = 0, wonAcc = 0, betsAcc = 0, implAcc = 0, offAcc = 0;
      const net = [], flatnet = [], hit = [], betrate = [], market = [];
      months.forEach((m, i) => {
        netAcc += netPer[i]; flatAcc += flatPer[i]; wonAcc += wonPer[i];
        betsAcc += betsPer[i]; implAcc += implPer[i];
        offAcc += (HIST.fights_by_month || {})[m] || 0;
        net.push(+netAcc.toFixed(2));
        flatnet.push(+flatAcc.toFixed(2));
        hit.push(betsAcc ? 100 * wonAcc / betsAcc : 0);
        betrate.push(offAcc ? 100 * betsAcc / offAcc : 0);
        market.push(betsAcc ? implAcc / betsAcc : 0);
      });
      out[r] = {net, flatnet, hit, betrate, market};
    }
    return out;
  }

  function drawHist() {
    // YR, not R: R is the chart's right margin in this scope
    const YR = yrRange(), single = YR[0] === YR[1], spanYears = +YR[1] - +YR[0] + 1;
    const metric = hMetricSel.value, def = METRIC_DEFS[metric];
    hSubEl.innerHTML = histMetricSub[metric]();
    hMonths = allMonths.filter(m => inRange(m, YR));
    if (!hActive.length || !hMonths.length) {
      // (no rules toggled on, or a year with no bets)
      hsvg.innerHTML = `<text x="${W / 2}" y="${H / 2}" text-anchor="middle">no rules selected — click a rule above to bring it back</text>`;
      return;
    }
    hSeries = computeHistSeries(hMonths);
    hCum = {}; for (const r of hActive) hCum[r] = hSeries[r][metric];
    const vals = hActive.flatMap(r => hCum[r]);
    const hMax = Math.max(metric === "net" || metric === "flatnet" ? 1 : 10, ...vals), hMin = Math.min(0, ...vals);
    hyS = v => T + (hMax - v) / (hMax - hMin || 1) * (H - T - B);
    hxS = i => L + i / Math.max(1, hMonths.length - 1) * (W - L - R);
    let hg = "";
    for (let i = 0; i <= 4; i++) {
      const v = hMin + (hMax - hMin) * i / 4, y = hyS(v);
      hg += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/>
             <text x="${L - 8}" y="${y + 4}" text-anchor="end">${def.axisFmt(v)}</text>`;
    }
    hg += `<line class="zero" x1="${L}" x2="${W - R}" y1="${hyS(0)}" y2="${hyS(0)}"/>`;
    hMonths.forEach((m, i) => {
      const label = single ? MN[+m.slice(5, 7) - 1]
        : (m.endsWith("-01") && (spanYears <= 8 || +m.slice(0, 4) % 2 === 1) ? m.slice(0, 4) : null);
      if (label) hg += `<text x="${hxS(i)}" y="${H - B + 18}" text-anchor="middle">${label}</text>`;
    });
    for (const r of hActive)
      hg += `<polyline class="s${r}" fill="none" stroke-width="2" stroke-linejoin="round"
              points="${hCum[r].map((v, i) => hxS(i).toFixed(1) + "," + hyS(v).toFixed(1)).join(" ")}"/>`;
    const hEnds = hActive.map(r => ({r, y: hyS(hCum[r][hMonths.length - 1])})).sort((a, b) => a.y - b.y);
    for (let i = 1; i < hEnds.length; i++)
      if (hEnds[i].y - hEnds[i - 1].y < 14) hEnds[i].y = hEnds[i - 1].y + 14;
    for (const e2 of hEnds)
      hg += `<text class="end-label t${e2.r}" x="${W - R + 8}" y="${e2.y + 4}">${e2.r} ${def.endFmt(hCum[e2.r][hMonths.length - 1])}</text>`;
    hg += `<line id="xhair" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="var(--axis)" stroke-dasharray="3,3" visibility="hidden"/>`;
    hsvg.innerHTML = hg;
  }
  drawHist();
  hMetricSel.addEventListener("change", drawHist);

  document.querySelectorAll("#hist-controls .lgbtn").forEach(b => b.addEventListener("click", () => {
    b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
    hActive = RULES.filter(r =>
      document.querySelector(`#hist-controls [data-r="${r}"]`).getAttribute("aria-pressed") === "true");
    drawHist();
  }));

  function histTipAt(e) {
    const xhair = hsvg.querySelector("#xhair");
    if (!xhair) return null;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(hsvg.getScreenCTM().inverse());
    if (pt.x < L || pt.x > W - R) { xhair.setAttribute("visibility", "hidden"); return null; }
    const i = Math.round((pt.x - L) / (W - L - R) * (hMonths.length - 1));
    xhair.setAttribute("x1", hxS(i)); xhair.setAttribute("x2", hxS(i));
    xhair.setAttribute("visibility", "visible");
    return `<div class="t">${hMonths[i]}</div>` + hActive.map(r => {
      const s = hSeries[r];
      return `<div class="row"><span>${RULE_NAME[r]}</span><span class="${cls(s.net[i])}">${sign$(s.net[i])} kelly / ${sign$(s.flatnet[i])} flat</span></div>
        <div class="row"><span>&nbsp;&nbsp;hit / bet rate</span><span>${s.hit[i].toFixed(0)}% / ${s.betrate[i].toFixed(0)}%</span></div>
        <div class="row"><span>&nbsp;&nbsp;avg market win</span><span>${s.market[i].toFixed(1)}%</span></div>`;
    }).join("");
  }
  hsvg.addEventListener("pointermove", e => {
    const html = histTipAt(e);
    html ? tipShow(html, e.clientX, e.clientY) : tipHide();
  });
  hsvg.addEventListener("click", e => {
    tipPinned = false;  // re-aim the crosshair even if already pinned
    const html = histTipAt(e);
    if (html) { tipShow(html, e.clientX, e.clientY, true); e.stopPropagation(); }
  });
  hsvg.addEventListener("pointerleave", () => { hsvg.querySelector("#xhair")?.setAttribute("visibility", "hidden"); tipHide(); });

  // per-rule replay summary (rebuilt per year filter)
  hbody.insertAdjacentHTML("beforeend", `<div class="card">
    <h2>Replay summary by rule</h2>
    <p class="sub">Same fights, three disciplines. Avg market win % is what the odds predicted for that rule's bets — a hit rate above it is where the profit comes from. Kelly ROI weights each bet by its kelly stake (how the weekly bankroll is actually split).</p>
    <div class="chart-scroll"><table id="hist-summary"></table></div>
  </div>`);
  function renderSummary(R) {
    document.getElementById("hist-summary").innerHTML =
      `<tr><th>Rule</th><th class="num">Bets</th><th class="num">Bet rate</th><th class="num">Hit rate</th><th class="num">Avg market win %</th><th class="num">Flat P/L ($1/bet)</th><th class="num">Flat ROI</th><th class="num">Kelly P/L (kelly of $1)</th><th class="num">Kelly ROI</th></tr>` +
      RULES.map(r => {
        const m = metrics(r, R), fights = fightsIn(R);
        if (!m.n) return `<tr><td><span class="rule-dot f${r}"></span>${RULE_NAME[r]}</td><td class="num">0</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td></tr>`;
        return `<tr><td><span class="rule-dot f${r}"></span>${RULE_NAME[r]}</td>
          <td class="num">${m.n.toLocaleString()}</td>
          <td class="num">${fights ? (100 * m.n / fights).toFixed(0) + "%" : "—"}</td>
          <td class="num">${m.hit.toFixed(1)}%</td>
          <td class="num" title="the hit rate the market predicted for these bets">${m.avgImp.toFixed(1)}%</td>
          <td class="num ${cls(m.flat)}">${sign$(m.flat)}</td>
          <td class="num ${cls(m.flat)}">${(m.flatROI >= 0 ? "+" : "") + m.flatROI.toFixed(1)}%</td>
          <td class="num ${cls(m.kellyPL)}" title="total kelly-staked: ${fmt$(m.kellyStaked)}">${sign$(m.kellyPL)}</td>
          <td class="num ${cls(m.kellyROI)}">${(m.kellyROI >= 0 ? "+" : "") + m.kellyROI.toFixed(1)}%</td></tr>`;
      }).join("");
  }

  // the literal bets, rule A, newest first (year filter from the tab)
  const rows = HIST.bets.A.slice().reverse();
  hbody.insertAdjacentHTML("beforeend", `<div class="card">
    <h2>Every rule-A bet, newest first</h2>
    <p class="sub">Market win % is the odds-implied probability (1/odds, vig included) — the win rate at which the bet breaks even. Both P/L columns are per $1 of bankroll: flat stakes the whole $1; Kelly stakes only the kelly-size share of it (capped 25%).</p>
    <div class="chart-scroll"><table id="bets-table">
      <tr><th>Date</th><th>Bet</th><th class="num">Odds</th><th class="num">Market win %</th><th class="num">Kelly size</th><th class="num">Flat P/L per $1</th><th class="num">Kelly P/L per $1</th><th></th></tr>
    </table></div>
    <p style="text-align:center;margin:12px 0 0"><button id="more-bets" style="cursor:pointer;background:var(--chip);color:var(--ink);border:1px solid var(--border);border-radius:5px;padding:7px 16px;font:600 13px system-ui">Show 50 more</button></p>
  </div>`);
  const table = document.getElementById("bets-table");
  const moreBtn = document.getElementById("more-bets");
  let shown = 0, filtered = rows;
  function renderMore() {
    const next = filtered.slice(shown, shown + 50);
    shown += next.length;
    table.insertAdjacentHTML("beforeend", next.map(b => {
      const [d, on, vs, odds, k, w] = b;
      const pl = w ? odds - 1 : -1;
      const kpl = pl * k;  // stake = kelly fraction of the $1
      const kfmt = (kpl >= 0 ? "+$" : "−$") +
        (Math.abs(kpl) >= 0.005 || kpl === 0 ? Math.abs(kpl).toFixed(2) : Math.abs(kpl).toFixed(3));
      return `<tr><td>${d}</td><td><strong>${esc(on)}</strong> <span style="color:var(--muted)">over ${esc(vs)}</span></td>
        <td class="num">${odds.toFixed(2)}</td>
        <td class="num">${(100 / odds).toFixed(1)}%</td>
        <td class="num">${(k * 100).toFixed(1)}%</td>
        <td class="num ${cls(pl)}">${sign$(pl)}</td>
        <td class="num ${cls(kpl)}">${kfmt}</td>
        <td style="padding-left:14px">${w ? "✅ won" : "❌ lost"}</td></tr>`;
    }).join(""));
    moreBtn.style.display = shown >= filtered.length ? "none" : "";
  }
  function resetTable() {
    // slice(1) not :not(:first-child): appended rows can land in a second
    // implicit tbody, whose own first row the selector would spare
    [...table.querySelectorAll("tr")].slice(1).forEach(tr => tr.remove());
    shown = 0; renderMore();
  }
  moreBtn.addEventListener("click", renderMore);

  // the one year range drives everything on the tab
  function applyRange() {
    const R = yrRange();
    renderTiles(R);
    drawHist();
    renderSummary(R);
    filtered = rows.filter(b => inRange(b[0], R));
    resetTable();
  }
  y1Sel.addEventListener("change", applyRange);
  y2Sel.addEventListener("change", applyRange);
  applyRange();
}

// -- data-dictionary search ------------------------------------------------
// with a query active, the tab shows ONLY the hits: matching definition rows
// (with their table + section heading) and matching inventory chips (with
// their group label). Everything else — prose, other sections — is hidden.
const dictDoc = document.querySelector("#tab-dictionary .doc");
const dictCount = document.getElementById("dict-count");
const isListP = p => {
  const chips = p.querySelectorAll("code");
  if (chips.length < 6) return false;
  const codeLen = [...chips].reduce((s, c) => s + c.textContent.length, 0);
  return codeLen / p.textContent.length >= 0.9;  // pure column lists, not prose
};
document.getElementById("dict-search").addEventListener("input", e => {
  const q = e.target.value.trim().toLowerCase();
  const els = [...dictDoc.children];
  if (!q) {
    els.forEach(el => { el.hidden = false; });
    dictDoc.querySelectorAll("tr").forEach(tr => { tr.hidden = false; });
    dictDoc.querySelectorAll("p code").forEach(c => { c.style.display = ""; });
    dictCount.textContent = "";
    return;
  }
  let hits = 0;
  const keep = new Set();
  els.forEach((el, i) => {
    let hit = false;
    if (el.tagName === "TABLE") {
      for (const tr of el.querySelectorAll("tr")) {
        if (tr.querySelector("th")) continue;
        const m = tr.textContent.toLowerCase().includes(q);
        tr.hidden = !m;
        if (m) { hits++; hit = true; }
      }
    } else if (el.tagName === "P" && isListP(el)) {
      for (const c of el.querySelectorAll("code")) {
        const t = c.textContent.toLowerCase();
        // two-way substring: searching avg_r_kd must light the `kd` chip
        // inside the avg_/med_ groups, and searching kd the reverse
        const m = t.includes(q) || q.includes(t);
        c.style.display = m ? "" : "none";
        if (m) { hits++; hit = true; }
      }
    }
    if (hit) {
      keep.add(el);
      // context: the group label right above a chip list, then the nearest
      // heading(s) walking upward — one h3 and one h2
      const prev = els[i - 1];
      if (prev && prev.tagName === "P" && prev.textContent.trim().endsWith(":")) keep.add(prev);
      let needH3 = true, needH2 = true;
      for (let j = i - 1; j >= 0 && (needH3 || needH2); j--) {
        const t = els[j].tagName;
        if (t === "H3" && needH3) { keep.add(els[j]); needH3 = false; }
        if (t === "H2") { if (needH2) keep.add(els[j]); needH2 = false; needH3 = false; }
        if (t === "H1") break;
      }
    }
  });
  els.forEach(el => { el.hidden = !keep.has(el); });
  dictCount.textContent = hits + " match" + (hits === 1 ? "" : "es");
});

// -- prose-doc search (methodology, FAQ): section-level filtering ----------
// a section = a heading (h1/h2/h3) plus everything until the next heading;
// matching sections stay whole, an h3 hit also keeps its parent h2 heading
function wireDocSearch(tab) {
  const doc = document.querySelector(`#tab-${tab} .doc`);
  const input = document.getElementById(`${tab}-search`);
  const countEl = document.getElementById(`${tab}-count`);
  const els = [...doc.children];
  const units = [];
  let cur = {h: null, els: [], parentH2: null}, lastH2 = null;
  for (const el of els) {
    if (/^H[123]$/.test(el.tagName)) {
      if (cur.h || cur.els.length) units.push(cur);
      if (el.tagName !== "H3") lastH2 = el;
      cur = {h: el, els: [], parentH2: el.tagName === "H3" ? lastH2 : null};
    } else cur.els.push(el);
  }
  units.push(cur);
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q) { els.forEach(el => { el.hidden = false; }); countEl.textContent = ""; return; }
    const keep = new Set();
    let hits = 0;
    for (const u of units) {
      const text = ((u.h ? u.h.textContent : "") + " " +
                    u.els.map(e => e.textContent).join(" ")).toLowerCase();
      if (!text.includes(q)) continue;
      hits++;
      if (u.h) keep.add(u.h);
      u.els.forEach(e => keep.add(e));
      if (u.parentH2) keep.add(u.parentH2);
    }
    els.forEach(el => { el.hidden = !keep.has(el); });
    countEl.textContent = hits + " section" + (hits === 1 ? "" : "s");
  });
}
wireDocSearch("methodology");
wireDocSearch("faq");

</script>
"""

if __name__ == "__main__":
    main()
