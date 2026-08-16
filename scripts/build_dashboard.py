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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="ledger.md")
    ap.add_argument("--out", default="dashboard.html")
    args = ap.parse_args()

    events = parse_ledger(args.ledger)
    data = {"events": events, "totals": summarise(events)}

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
            .replace("__UPDATED__", aest.strftime("%-d %b %Y, %-I:%M %p AEST"))
            .replace("__FAQ__", docs_html["faq"])
            .replace("__METHODOLOGY__", docs_html["methodology"])
            .replace("__DICTIONARY__", docs_html["dictionary"]))
    open(args.out, "w").write(html)
    print(f"wrote {args.out}: {len(events)} scored event(s)")


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
    <button role="tab" data-tab="methodology" aria-selected="false">Methodology</button>
    <button role="tab" data-tab="dictionary" aria-selected="false">Data dictionary</button>
    <button role="tab" data-tab="faq" aria-selected="false">FAQ</button>
  </nav>
</header>

<main>
  <section id="tab-performance" role="tabpanel">
    <div class="tiles" id="tiles"></div>
    <div id="charts"></div>

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

  <section id="tab-methodology" role="tabpanel" hidden><article class="doc">__METHODOLOGY__</article></section>
  <section id="tab-dictionary" role="tabpanel" hidden><article class="doc">__DICTIONARY__</article></section>
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
