#!/usr/bin/env python3
"""Build dashboard.html: the betting-performance dashboard + docs, one file.

Reads ledger.md (the entry-9 A/C/E record appended by score_card.py on the
weekly-predictions-log branch) and the three docs/*.md, and emits a single
self-contained HTML page: a Performance tab (charts + tables driven by an
embedded JSON blob) and one tab per doc. No network access at view time — the
Friday scoring Routine regenerates the file and republishes it as an Artifact
after each card is graded.

Usage (from repo root, with ledger.md checked out of the log branch):
    python3 scripts/build_dashboard.py [--ledger ledger.md] [--out dashboard.html]

A missing/empty ledger is fine: the Performance tab renders its empty state
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

ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|([^|]+)\|\s*([ACE])\s*"
                 r"\|\s*\$([\d.]+)\s*\|\s*\$([\d.]+)\s*\|\s*([+-][\d.]+)\s*"
                 r"\|\s*(\d+)/(\d+)/(\d+)\s*\|")


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
        index[key]["rules"][rule] = {
            "staked": float(m.group(4)), "returned": float(m.group(5)),
            "net": float(m.group(6)), "won": int(m.group(7)),
            "placed": int(m.group(8)), "void": int(m.group(9))}
    return sorted(events, key=lambda e: e["date"])


def summarise(events):
    total = {r: {"staked": 0.0, "returned": 0.0, "won": 0, "placed": 0,
                 "void": 0, "ahead": 0} for r in "ACE"}
    for e in events:
        for r, row in e["rules"].items():
            t = total[r]
            for k in ("staked", "returned", "won", "placed", "void"):
                t[k] += row[k]
            if r != "A" and "A" in e["rules"] and row["net"] > e["rules"]["A"]["net"]:
                t["ahead"] += 1
    for r, t in total.items():
        t["net"] = round(t["returned"] - t["staked"], 2)
        t["roi"] = round(100 * t["net"] / t["staked"], 1) if t["staked"] else None
        t["hit"] = round(100 * t["won"] / t["placed"], 1) if t["placed"] else None
    return total


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

    bets = {"A": [], "C": [], "E": []}
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
    return {"fights": len(df), "span": [df["date_d"].min().strftime("%Y-%m-%d"),
                                        df["date_d"].max().strftime("%Y-%m-%d")],
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
    --sA: #2a78d6; --sC: #eb6834; --sE: #1baf7a;
    --good: #006300; --bad: #d03b3b; --chip: #f0efec;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
      --muted: #898781; --grid: #2c2c2a; --axis: #383835;
      --border: rgba(255,255,255,0.10);
      --sA: #3987e5; --sC: #d95926; --sE: #199e70;
      --good: #0ca30c; --bad: #e66767; --chip: #262624;
    }
  }
  :root[data-theme="dark"] {
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
    --muted: #898781; --grid: #2c2c2a; --axis: #383835;
    --border: rgba(255,255,255,0.10);
    --sA: #3987e5; --sC: #d95926; --sE: #199e70;
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
  .legend span::before { content: ""; display: inline-block; width: 9px; height: 9px;
            border-radius: 2px; margin-right: 6px; }
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
  svg text { font: 11.5px system-ui, sans-serif; fill: var(--muted); }
  svg .end-label { font-weight: 700; font-size: 12px; }
  svg .end-label.tA { fill: var(--sA); } svg .end-label.tC { fill: var(--sC); }
  svg .end-label.tE { fill: var(--sE); }
  .sA { stroke: var(--sA); } .sC { stroke: var(--sC); } .sE { stroke: var(--sE); }
  .fA { fill: var(--sA); } .fC { fill: var(--sC); } .fE { fill: var(--sE); }
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
    <button role="tab" data-tab="trial" aria-selected="false">Live trial</button>
    <button role="tab" data-tab="history" aria-selected="false">History</button>
    <button role="tab" data-tab="methodology" aria-selected="false">Methodology</button>
    <button role="tab" data-tab="dictionary" aria-selected="false">Data dictionary</button>
    <button role="tab" data-tab="faq" aria-selected="false">FAQ</button>
  </nav>
</header>

<main>
  <section id="tab-performance" role="tabpanel">
    <div class="tiles" id="tiles"></div>
    <div id="charts"></div>
  </section>

  <section id="tab-trial" role="tabpanel" hidden>
    <div class="card" style="margin-top:0">
      <h2>The experiment</h2>
      <p class="sub" style="margin-bottom:0">Rule A (kelly-proportional value betting) is staked with real money every card. Two challengers that looked better in the recent backtest — C, which ignores edges smaller than the bookmaker's margin, and E, which shrinks the model's probability halfway toward the market's before betting — run as shadows on identical cards. Neither was promotable from the backtest alone (winner's-curse risk), so the tiebreak runs prospectively, below.</p>
    </div>

    <div class="card">
      <h2>Rule comparison &middot; live record</h2>
      <p class="sub">Rule A is staked with real money; C (vig floor) and E (shrunk staking) are shadow-logged on identical cards.</p>
      <div class="chart-scroll"><table id="rule-table"></table></div>
    </div>

    <div class="card">
      <h2>Promotion trial</h2>
      <p class="sub">Pre-registered (EXPERIMENTS.md entry 9): after 10 scored events, a shadow rule replaces A only if it leads on cumulative return <em>and</em> was ahead on at least 6 cards. Filled squares are scored events.</p>
      <div class="slots" id="slots"></div>
    </div>

    <div class="card">
      <h2>Backtest reference &middot; why C and E are being trialled</h2>
      <p class="sub">5,786 historical fights at closing odds (entry 9). H2 = the more recent half. All ROIs are upper bounds.</p>
      <div class="chart-scroll"><table>
        <tr><th>Rule</th><th class="num">Bets</th><th class="num">Hit</th><th class="num">Flat ROI</th><th class="num">Kelly ROI</th><th class="num">H2 flat</th></tr>
        <tr><td><span class="rule-dot fA"></span>A &mdash; kelly value (staked)</td><td class="num">4,536</td><td class="num">55.9%</td><td class="num">+6.1%</td><td class="num">+14.0%</td><td class="num">+0.9%</td></tr>
        <tr><td><span class="rule-dot fC"></span>C &mdash; vig floor (shadow)</td><td class="num">3,288</td><td class="num">54.6%</td><td class="num">+9.4%</td><td class="num">+16.0%</td><td class="num">+8.0%</td></tr>
        <tr><td><span class="rule-dot fE"></span>E &mdash; shrunk staking (shadow)</td><td class="num">3,340</td><td class="num">54.6%</td><td class="num">+9.2%</td><td class="num">+27.9%</td><td class="num">+7.4%</td></tr>
      </table></div>
    </div>
  </section>

  <section id="tab-history" role="tabpanel" hidden>
    <div class="tiles" id="hist-tiles"></div>
    <div id="hist-body"></div>
  </section>

  <section id="tab-methodology" role="tabpanel" hidden><article class="doc">__METHODOLOGY__</article></section>
  <section id="tab-dictionary" role="tabpanel" hidden>
    <p style="max-width:72ch;margin:0 0 4px">
      <input id="dict-search" type="search" placeholder="Search columns and definitions — e.g. elo, avg_r_kd, layoff"
        style="width:100%;padding:9px 12px;font:14px system-ui;color:var(--ink);background:var(--surface);border:1px solid var(--border);border-radius:6px">
      <span id="dict-count" class="stamp"></span>
    </p>
    <article class="doc">__DICTIONARY__</article>
  </section>
  <section id="tab-faq" role="tabpanel" hidden><article class="doc">__FAQ__</article></section>
</main>
<footer>Rebuilt by the Friday scoring Routine from <code>ledger.md</code> on the weekly-predictions-log branch.</footer>
<div id="tooltip"></div>

<script>
const DATA = __DATA__;
const RULES = ["A", "C", "E"];
const RULE_NAME = {A: "A · kelly value", C: "C · vig floor", E: "E · shrunk"};
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
const tip = document.getElementById("tooltip");
function tipShow(html, x, y) {
  tip.innerHTML = html; tip.style.display = "block";
  const w = tip.offsetWidth, vw = window.innerWidth;
  tip.style.left = Math.min(x + 14, vw - w - 8) + "px";
  tip.style.top = (y + 14) + "px";
}
function tipHide() { tip.style.display = "none"; }

// -- summary tiles ---------------------------------------------------------
const ev = DATA.events, tot = DATA.totals;
const n = ev.length, A = tot.A;
const tiles = document.getElementById("tiles");
function tile(k, v, s, vClass) {
  tiles.insertAdjacentHTML("beforeend",
    `<div class="tile"><div class="k">${k}</div><div class="v ${vClass || ""}">${v}</div><div class="s">${s}</div></div>`);
}
if (n) {
  tile("Rule A net", sign$(A.net), fmt$(A.staked) + " staked → " + fmt$(A.returned) + " back", cls(A.net));
  tile("Rule A ROI", (A.roi >= 0 ? "+" : "") + A.roi + "%", "on money actually staked", cls(A.roi));
  tile("Rule A hit rate", A.hit + "%", A.won + " of " + A.placed + " bets won" + (A.void ? ", " + A.void + " void" : ""));
  const lead = RULES.map(r => [r, tot[r].net]).sort((a, b) => b[1] - a[1])[0];
  tile("Trial progress", n + " / 10", "leader so far: rule " + lead[0] + " (" + sign$(lead[1]) + ")");
} else {
  tile("Rule A net", "—", "no events scored yet");
  tile("Rule A ROI", "—", "no events scored yet");
  tile("Rule A hit rate", "—", "no bets graded yet");
  tile("Trial progress", "0 / 10", "first grading pending");
}

// -- charts ----------------------------------------------------------------
const charts = document.getElementById("charts");
function card(title, sub) {
  const d = document.createElement("div"); d.className = "card";
  d.innerHTML = `<h2>${title}</h2><p class="sub">${sub}</p>
    <div class="legend"><span class="lA">A &middot; staked</span><span class="lC">C &middot; shadow</span><span class="lE">E &middot; shadow</span></div>`;
  charts.appendChild(d); return d;
}
const shortName = t => esc(t.replace(/^UFC (Fight Night|on \w+)[:\s]*/i, "").split(":")[0].trim());

if (!n) {
  charts.insertAdjacentHTML("beforeend",
    `<div class="empty"><strong>No events scored yet.</strong><br>
     The Friday Routine grades each completed card and fills this page in —
     the cumulative-return and per-event charts appear after the first grading.</div>`);
} else {
  // cumulative net line chart, x = events (a $0 start point makes n=1 drawable)
  const W = 940, H = 300, L = 46, R = 76, T = 16, B = 40;
  const cum = {};
  for (const r of RULES) {
    let acc = 0;
    cum[r] = [0].concat(ev.map(e => acc += (e.rules[r] ? e.rules[r].net : 0)));
  }
  const allY = RULES.flatMap(r => cum[r]).concat(ev.flatMap(e => RULES.map(r => e.rules[r] ? e.rules[r].net : 0)));
  const yMax = Math.max(5, ...allY), yMin = Math.min(0, ...allY);
  const pad = (yMax - yMin) * 0.08;
  const ySc = v => T + (yMax + pad - v) / (yMax + pad - yMin + pad) * (H - T - B);
  const xSc = i => L + i / Math.max(1, n) * (W - L - R);

  let g = "", ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const v = yMin + (yMax - yMin) * i / ticks, y = ySc(v);
    g += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/>
          <text x="${L - 8}" y="${y + 4}" text-anchor="end">${(v < 0 ? "−$" : "$") + Math.abs(Math.round(v))}</text>`;
  }
  g += `<line class="zero" x1="${L}" x2="${W - R}" y1="${ySc(0)}" y2="${ySc(0)}"/>`;
  g += `<text x="${xSc(0)}" y="${H - B + 18}" text-anchor="middle">start</text>`;
  ev.forEach((e, i) => {
    g += `<text x="${xSc(i + 1)}" y="${H - B + 18}" text-anchor="middle">${shortName(e.event)}</text>`;
  });
  for (const r of RULES) {
    const pts = cum[r].map((v, i) => xSc(i).toFixed(1) + "," + ySc(v).toFixed(1)).join(" ");
    g += `<polyline class="s${r}" points="${pts}" fill="none" stroke-width="2" stroke-linejoin="round"/>`;
    cum[r].forEach((v, i) => {
      if (i === 0) return;
      g += `<circle class="f${r} pt" data-r="${r}" data-i="${i - 1}" cx="${xSc(i)}" cy="${ySc(v)}" r="4.5" stroke="var(--surface)" stroke-width="2"/>`;
    });
  }
  // direct end labels, nudged apart if they collide (relief for light-mode aqua)
  const ends = RULES.map(r => ({r, y: ySc(cum[r][n])})).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++)
    if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  for (const e2 of ends)
    g += `<text class="end-label t${e2.r}" x="${W - R + 8}" y="${e2.y + 4}">${e2.r} ${sign$(cum[e2.r][n])}</text>`;

  const c1 = card("Cumulative return by event", "Running net profit per rule across scored cards — every rule replays the same $50 bankroll each event.");
  c1.insertAdjacentHTML("beforeend",
    `<div class="chart-scroll"><svg id="cumchart" viewBox="0 0 ${W} ${H}" style="min-width:640px;width:100%">${g}</svg></div>`);
  c1.addEventListener("pointermove", e => {
    const t = e.target.closest(".pt");
    if (!t) return tipHide();
    const i = +t.dataset.i, r = t.dataset.r, row = ev[i].rules[r];
    tipShow(`<div class="t">${esc(ev[i].event)}</div>
      <div class="row"><span>${RULE_NAME[r]}</span><span class="${cls(row.net)}">${sign$(row.net)}</span></div>
      <div class="row"><span>staked → returned</span><span>${fmt$(row.staked)} → ${fmt$(row.returned)}</span></div>
      <div class="row"><span>bets</span><span>${row.won}/${row.placed} won${row.void ? ", " + row.void + " void" : ""}</span></div>
      <div class="row"><span>cumulative</span><span class="${cls(cum[r][i + 1])}">${sign$(cum[r][i + 1])}</span></div>`,
      e.clientX, e.clientY);
  });
  c1.addEventListener("pointerleave", tipHide);

  // per-event net, grouped bars
  const H2 = 240, bw = Math.min(26, (W - L - R) / n / 4);
  let b = "";
  for (let i = 0; i <= ticks; i++) {
    const v = yMin + (yMax - yMin) * i / ticks;
    const y = T + (yMax + pad - v) / (yMax + pad - yMin + pad) * (H2 - T - B);
    b += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/>
          <text x="${L - 8}" y="${y + 4}" text-anchor="end">${(v < 0 ? "−$" : "$") + Math.abs(Math.round(v))}</text>`;
  }
  const ySc2 = v => T + (yMax + pad - v) / (yMax + pad - yMin + pad) * (H2 - T - B);
  b += `<line class="zero" x1="${L}" x2="${W - R}" y1="${ySc2(0)}" y2="${ySc2(0)}"/>`;
  ev.forEach((e, i) => {
    const cx = L + (i + 0.5) / n * (W - L - R);
    b += `<text x="${cx}" y="${H2 - B + 18}" text-anchor="middle">${shortName(e.event)}</text>`;
    RULES.forEach((r, j) => {
      const row = e.rules[r]; if (!row) return;
      const x = cx + (j - 1) * (bw + 2) - bw / 2;
      const y0 = ySc2(0), y1 = ySc2(row.net);
      const top = Math.min(y0, y1), h = Math.max(2, Math.abs(y0 - y1));
      const rx = `rx="4"`;
      b += `<rect class="f${r} bar" data-r="${r}" data-i="${i}" x="${x.toFixed(1)}" y="${top.toFixed(1)}"
             width="${bw}" height="${h.toFixed(1)}" ${rx}/>`;
    });
  });
  const c2 = card("Net per event", "Each card graded independently: what the $50 came back as, minus the $50, per rule.");
  c2.insertAdjacentHTML("beforeend",
    `<div class="chart-scroll"><svg viewBox="0 0 ${W} ${H2}" style="min-width:640px;width:100%">${b}</svg></div>`);
  c2.addEventListener("pointermove", e => {
    const t = e.target.closest(".bar");
    if (!t) return tipHide();
    const i = +t.dataset.i, r = t.dataset.r, row = ev[i].rules[r];
    tipShow(`<div class="t">${esc(ev[i].event)}</div>
      <div class="row"><span>${RULE_NAME[r]}</span><span class="${cls(row.net)}">${sign$(row.net)}</span></div>
      <div class="row"><span>staked → returned</span><span>${fmt$(row.staked)} → ${fmt$(row.returned)}</span></div>
      <div class="row"><span>hit</span><span>${row.won}/${row.placed}${row.void ? " (+" + row.void + " void)" : ""}</span></div>`,
      e.clientX, e.clientY);
  });
  c2.addEventListener("pointerleave", tipHide);
}

// -- rule table ------------------------------------------------------------
const rt = document.getElementById("rule-table");
rt.innerHTML = `<tr><th>Rule</th><th class="num">Events</th><th class="num">Staked</th>
  <th class="num">Returned</th><th class="num">Net</th><th class="num">ROI</th>
  <th class="num">Hit rate</th><th class="num">Cards ahead of A</th></tr>` +
  RULES.map(r => {
    const t = tot[r];
    return `<tr><td><span class="rule-dot f${r}"></span>${RULE_NAME[r]}${r === "A" ? " (staked)" : " (shadow)"}</td>
      <td class="num">${n}</td>
      <td class="num">${n ? fmt$(t.staked) : "—"}</td>
      <td class="num">${n ? fmt$(t.returned) : "—"}</td>
      <td class="num ${n ? cls(t.net) : ""}">${n ? sign$(t.net) : "—"}</td>
      <td class="num ${n ? cls(t.net) : ""}">${t.roi === null ? "—" : (t.roi >= 0 ? "+" : "") + t.roi + "%"}</td>
      <td class="num">${t.hit === null ? "—" : t.hit + "% (" + t.won + "/" + t.placed + ")"}</td>
      <td class="num">${r === "A" ? "—" : n ? t.ahead + " / " + n : "—"}</td></tr>`;
  }).join("");

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
  // metrics per rule: flat = $1 per bet; kelly = stake-proportional, per $100
  const M = {};
  for (const r of RULES) {
    const b = HIST.bets[r];
    let flat = 0, kst = 0, kpr = 0, won = 0;
    for (const row of b) {
      const [odds, k, w] = row.slice(-3);
      flat += w ? odds - 1 : -1;
      kst += k; kpr += w ? k * (odds - 1) : -k; won += w;
    }
    M[r] = {n: b.length, hit: 100 * won / b.length, flat, flatROI: 100 * flat / b.length,
            kellyROI: 100 * kpr / kst};
  }
  const yrs = (new Date(HIST.span[1]).getFullYear() - new Date(HIST.span[0]).getFullYear());
  htile("Fights with odds", HIST.fights.toLocaleString(), HIST.span[0].slice(0, 4) + "–" + HIST.span[1].slice(0, 4) + " (" + yrs + " years)");
  htile("Rule A bets", M.A.n.toLocaleString(), M.A.hit.toFixed(1) + "% hit rate");
  htile("Flat $1 per bet", sign$(M.A.flat), M.A.flatROI.toFixed(1) + "% ROI on " + M.A.n.toLocaleString() + " × $1", cls(M.A.flat));
  htile("Kelly ROI", (M.A.kellyROI >= 0 ? "+" : "") + M.A.kellyROI.toFixed(1) + "%", "stake-weighted, uncompounded", cls(M.A.kellyROI));

  // cumulative flat profit by month, filterable by rule and year
  const W = 940, H = 320, L = 52, R = 86, T = 16, B = 34;
  const allMonths = [...new Set(RULES.flatMap(r => HIST.bets[r].map(b => b[0].slice(0, 7))))].sort();
  const histYears = [...new Set(allMonths.map(m => m.slice(0, 4)))];
  const MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  hbody.insertAdjacentHTML("beforeend", `<div class="card">
    <h2>If we'd bet $1 on every value bet since ${HIST.span[0].slice(0, 4)}</h2>
    <p class="sub">Cumulative profit, $1 flat per bet, each rule applied to the same ${HIST.fights.toLocaleString()} fights (pooled out-of-fold predictions — the model never trained on the fight it predicts — matched to closing odds). Upper bounds: closing-odds conditioning, no line movement. Click a rule to toggle it; picking a year restarts the running total at $0 for that year.</p>
    <div class="legend" id="hist-controls">
      <button class="lgbtn lA" data-r="A" aria-pressed="true">A &middot; kelly value</button>
      <button class="lgbtn lC" data-r="C" aria-pressed="true">C &middot; vig floor</button>
      <button class="lgbtn lE" data-r="E" aria-pressed="true">E &middot; shrunk</button>
      <select id="hist-yr"><option value="">All years</option>${histYears.map(y => `<option>${y}</option>`).join("")}</select>
    </div>
    <div class="chart-scroll"><svg id="histchart" viewBox="0 0 ${W} ${H}" style="min-width:640px;width:100%"></svg></div>
  </div>`);
  const hsvg = document.getElementById("histchart");
  const yrSelH = document.getElementById("hist-yr");
  let hMonths = [], hCum = {}, hActive = [...RULES];
  let hxS = i => i, hyS = v => v;

  function drawHist() {
    const yr = yrSelH.value;
    hMonths = allMonths.filter(m => !yr || m.startsWith(yr));
    if (!hActive.length || !hMonths.length) {
      hsvg.innerHTML = `<text x="${W / 2}" y="${H / 2}" text-anchor="middle">no rules selected — click a rule above to bring it back</text>`;
      return;
    }
    const mi = new Map(hMonths.map((m, i) => [m, i]));
    hCum = {};
    for (const r of hActive) {
      const per = new Array(hMonths.length).fill(0);
      for (const row of HIST.bets[r]) {
        const key = row[0].slice(0, 7);
        if (!mi.has(key)) continue;
        const [odds, , w] = row.slice(-3);
        per[mi.get(key)] += w ? odds - 1 : -1;
      }
      let acc = 0;
      hCum[r] = per.map(v => +(acc += v).toFixed(2));
    }
    const vals = hActive.flatMap(r => hCum[r]);
    const hMax = Math.max(1, ...vals), hMin = Math.min(0, ...vals);
    hyS = v => T + (hMax - v) / (hMax - hMin || 1) * (H - T - B);
    hxS = i => L + i / Math.max(1, hMonths.length - 1) * (W - L - R);
    let hg = "";
    for (let i = 0; i <= 4; i++) {
      const v = hMin + (hMax - hMin) * i / 4, y = hyS(v);
      hg += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/>
             <text x="${L - 8}" y="${y + 4}" text-anchor="end">${(v < 0 ? "−$" : "$") + Math.abs(Math.round(v))}</text>`;
    }
    hg += `<line class="zero" x1="${L}" x2="${W - R}" y1="${hyS(0)}" y2="${hyS(0)}"/>`;
    hMonths.forEach((m, i) => {
      const label = yr ? MN[+m.slice(5, 7) - 1]
        : (m.endsWith("-01") && +m.slice(0, 4) % 2 === 1 ? m.slice(0, 4) : null);
      if (label) hg += `<text x="${hxS(i)}" y="${H - B + 18}" text-anchor="middle">${label}</text>`;
    });
    for (const r of hActive)
      hg += `<polyline class="s${r}" fill="none" stroke-width="2" stroke-linejoin="round"
              points="${hCum[r].map((v, i) => hxS(i).toFixed(1) + "," + hyS(v).toFixed(1)).join(" ")}"/>`;
    const hEnds = hActive.map(r => ({r, y: hyS(hCum[r][hMonths.length - 1])})).sort((a, b) => a.y - b.y);
    for (let i = 1; i < hEnds.length; i++)
      if (hEnds[i].y - hEnds[i - 1].y < 14) hEnds[i].y = hEnds[i - 1].y + 14;
    for (const e2 of hEnds)
      hg += `<text class="end-label t${e2.r}" x="${W - R + 8}" y="${e2.y + 4}">${e2.r} ${sign$(hCum[e2.r][hMonths.length - 1])}</text>`;
    hg += `<line id="xhair" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="var(--axis)" stroke-dasharray="3,3" visibility="hidden"/>`;
    hsvg.innerHTML = hg;
  }
  drawHist();

  document.querySelectorAll("#hist-controls .lgbtn").forEach(b => b.addEventListener("click", () => {
    b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
    hActive = RULES.filter(r =>
      document.querySelector(`#hist-controls [data-r="${r}"]`).getAttribute("aria-pressed") === "true");
    drawHist();
  }));
  yrSelH.addEventListener("change", drawHist);

  hsvg.addEventListener("pointermove", e => {
    const xhair = hsvg.querySelector("#xhair");
    if (!xhair) return;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(hsvg.getScreenCTM().inverse());
    if (pt.x < L || pt.x > W - R) { xhair.setAttribute("visibility", "hidden"); return tipHide(); }
    const i = Math.round((pt.x - L) / (W - L - R) * (hMonths.length - 1));
    xhair.setAttribute("x1", hxS(i)); xhair.setAttribute("x2", hxS(i));
    xhair.setAttribute("visibility", "visible");
    tipShow(`<div class="t">${hMonths[i]}</div>` + hActive.map(r =>
      `<div class="row"><span>${RULE_NAME[r]}</span><span class="${cls(hCum[r][i])}">${sign$(hCum[r][i])}</span></div>`).join(""),
      e.clientX, e.clientY);
  });
  hsvg.addEventListener("pointerleave", () => { hsvg.querySelector("#xhair")?.setAttribute("visibility", "hidden"); tipHide(); });

  // per-rule replay summary
  hbody.insertAdjacentHTML("beforeend", `<div class="card">
    <h2>Replay summary by rule</h2>
    <p class="sub">Same fights, three disciplines. Kelly ROI weights each bet by its kelly stake (how the weekly bankroll is actually split).</p>
    <div class="chart-scroll"><table>
      <tr><th>Rule</th><th class="num">Bets</th><th class="num">Bet rate</th><th class="num">Hit</th><th class="num">Flat P/L ($1/bet)</th><th class="num">Flat ROI</th><th class="num">Kelly ROI</th></tr>
      ${RULES.map(r => `<tr><td><span class="rule-dot f${r}"></span>${RULE_NAME[r]}</td>
        <td class="num">${M[r].n.toLocaleString()}</td>
        <td class="num">${(100 * M[r].n / HIST.fights).toFixed(0)}%</td>
        <td class="num">${M[r].hit.toFixed(1)}%</td>
        <td class="num ${cls(M[r].flat)}">${sign$(M[r].flat)}</td>
        <td class="num ${cls(M[r].flat)}">${(M[r].flatROI >= 0 ? "+" : "") + M[r].flatROI.toFixed(1)}%</td>
        <td class="num ${cls(M[r].kellyROI)}">${(M[r].kellyROI >= 0 ? "+" : "") + M[r].kellyROI.toFixed(1)}%</td></tr>`).join("")}
    </table></div>
  </div>`);

  // the literal bets, rule A, newest first
  const rows = HIST.bets.A.slice().reverse();
  hbody.insertAdjacentHTML("beforeend", `<div class="card">
    <h2>Every rule-A bet, newest first</h2>
    <p class="sub">${rows.length.toLocaleString()} bets. Both P/L columns are per $1 of bankroll: flat stakes the whole $1; Kelly stakes only the kelly-size share of it (capped 25%). <select id="yr-filter"><option value="">All years</option></select></p>
    <div class="chart-scroll"><table id="bets-table">
      <tr><th>Date</th><th>Bet</th><th class="num">Odds</th><th class="num">Kelly size</th><th class="num">Flat P/L per $1</th><th class="num">Kelly P/L per $1</th><th></th></tr>
    </table></div>
    <p style="text-align:center;margin:12px 0 0"><button id="more-bets" style="cursor:pointer;background:var(--chip);color:var(--ink);border:1px solid var(--border);border-radius:5px;padding:7px 16px;font:600 13px system-ui">Show 50 more</button></p>
  </div>`);
  const table = document.getElementById("bets-table");
  const moreBtn = document.getElementById("more-bets");
  const yrSel = document.getElementById("yr-filter");
  [...new Set(rows.map(b => b[0].slice(0, 4)))].forEach(y =>
    yrSel.insertAdjacentHTML("beforeend", `<option>${y}</option>`));
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
        <td class="num">${odds.toFixed(2)}</td><td class="num">${(k * 100).toFixed(1)}%</td>
        <td class="num ${cls(pl)}">${sign$(pl)}</td>
        <td class="num ${cls(kpl)}">${kfmt}</td>
        <td style="padding-left:14px">${w ? "✅ won" : "❌ lost"}</td></tr>`;
    }).join(""));
    moreBtn.style.display = shown >= filtered.length ? "none" : "";
  }
  function resetTable() {
    table.querySelectorAll("tr:not(:first-child)").forEach(tr => tr.remove());
    shown = 0; renderMore();
  }
  yrSel.addEventListener("change", () => {
    filtered = yrSel.value ? rows.filter(b => b[0].startsWith(yrSel.value)) : rows;
    resetTable();
  });
  moreBtn.addEventListener("click", renderMore);
  renderMore();
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

// -- promotion slots -------------------------------------------------------
const slots = document.getElementById("slots");
for (let i = 0; i < 10; i++) {
  const e = ev[i];
  slots.insertAdjacentHTML("beforeend", e
    ? `<div class="slot done" title="${esc(e.event)} (${e.date})"><span class="n">${i + 1}</span>${e.date.slice(5)}</div>`
    : `<div class="slot"><span class="n">${i + 1}</span></div>`);
}
</script>
"""

if __name__ == "__main__":
    main()
