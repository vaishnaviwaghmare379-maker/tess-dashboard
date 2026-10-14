"""
TESS Enterprise World Model - one-click dashboard.

    python dashboard.py

Builds the world model, runs the LLM layer and the evaluation, writes
index.html next to this file and opens it in your browser.
No extra libraries required. index.html is self-contained, so you can also
host it as-is (GitHub Pages, Netlify, ...).
"""
import json
import webbrowser
from dataclasses import asdict
from pathlib import Path

from modules.org_data import EVENTS
from modules.llm_layer import USE_LLM, rewrite_online, rewrite_offline
from modules.evaluate import build_world, build_questions, search_answer, MESSY, TODAY

NOTES = {
    3: "Search cannot tell that the newer message replaces the older one, so it returns both owners.",
    4: "Search lists a task that was fixed later and misses one described as 'stuck' instead of 'blocked'.",
    5: "The answer needs two hops (Auth service, then Payment gateway). No single message says it.",
    10: "The answer is spread over two facts: which meeting discussed the document, and who attended it.",
}


def collect():
    wm = build_world()

    # ---- raw event stream (+ what the LLM layer understood for messy ones) ----
    events = [{"date": d, "source": s, "text": t, "clean": None} for d, s, t in EVENTS]
    rewrite = rewrite_online if USE_LLM else rewrite_offline
    for d, t in MESSY:
        events.append({"date": d, "source": "messy", "text": t, "clean": rewrite(wm, t)})
    events.sort(key=lambda e: e["date"])

    # ---- evaluation ----
    rows, g_score, s_score = [], 0, 0
    for i, (q, date, subj, etype, graph_fn, truth) in enumerate(build_questions(wm), 1):
        g = set(graph_fn(date))
        s = search_answer(wm, q, subj, etype, date)
        g_ok, s_ok = g == truth, s == truth
        g_score += g_ok
        s_score += s_ok
        rows.append({"n": i, "q": q, "date": date, "truth": sorted(truth),
                     "graph": sorted(g), "graph_ok": g_ok,
                     "search": sorted(s), "search_ok": s_ok,
                     "note": "" if s_ok else NOTES.get(i, "")})

    return {
        "mode": "ONLINE (Claude)" if USE_LLM else "OFFLINE (rule-based stand-in)",
        "minDate": min(e["date"] for e in events),
        "maxDate": TODAY,
        "entities": [asdict(e) for e in wm.entities.values()],
        "edges": [asdict(e) for e in wm.edges],
        "events": events,
        "eval": {"rows": rows, "graph": g_score, "search": s_score, "total": len(rows)},
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TESS - Enterprise World Model</title>
<style>
:root{--bg:#f4f6fb;--card:#fff;--ink:#1d2433;--mute:#667085;--line:#e3e7ef;--accent:#3b6fe0;--good:#1f9d55;--bad:#d62828;--warn:#b7791f}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink);line-height:1.5}
header{background:#1d2433;color:#fff;padding:18px 28px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
header h1{font-size:20px;margin:0;font-weight:650}
header .sub{color:#aab3c5;font-size:13px}
.badge{margin-left:auto;background:#2f3b57;border-radius:999px;padding:4px 12px;font-size:12px}
nav{display:flex;gap:4px;padding:10px 20px 0;background:#fff;border-bottom:1px solid var(--line);flex-wrap:wrap;position:sticky;top:0;z-index:5}
nav button{border:0;background:none;padding:10px 16px;font-size:14px;cursor:pointer;color:var(--mute);border-bottom:3px solid transparent;font-weight:550}
nav button.on{color:var(--accent);border-color:var(--accent)}
main{max-width:1180px;margin:0 auto;padding:24px 20px 60px}
section{display:none}section.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:18px}
.card h3{margin:0 0 10px;font-size:16px}
.grid{display:grid;gap:16px}.g4{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}.g2{grid-template-columns:repeat(auto-fit,minmax(480px,1fr))}
.stat{text-align:center}.stat b{display:block;font-size:30px;color:var(--accent)}.stat span{color:var(--mute);font-size:13px}
.flow{display:flex;gap:8px;align-items:stretch;flex-wrap:wrap}
.flow div{flex:1;min-width:150px;background:#eef3ff;border:1px solid #d5e0fb;border-radius:10px;padding:12px;font-size:13px}
.flow div b{display:block;margin-bottom:4px}.flow i{align-self:center;color:var(--mute);font-style:normal;font-size:20px}
.row{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
label{font-size:13px;color:var(--mute)}
select,input[type=range]{font-size:14px}select{padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;max-width:100%}
input[type=range]{width:260px}
.dt{font-weight:650;font-size:16px;min-width:100px;display:inline-block}
button.btn{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:8px 14px;cursor:pointer;font-size:14px}
svg{width:100%;height:auto;background:#fff;border:1px solid var(--line);border-radius:10px}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--mute);margin-top:8px}
.legend span i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px;border:1px solid #888}
.chg{padding:5px 10px;border-radius:8px;margin:4px 0;font-size:13.5px;font-family:ui-monospace,Consolas,monospace}
.chg.add{background:#e8f6ee}.chg.del{background:#fdeaea}.chg.mod{background:#fff6e0}
.feed{max-height:340px;overflow:auto;font-size:13.5px}
.feed div{padding:6px 0;border-bottom:1px solid var(--line)}
.tag{display:inline-block;font-size:11px;background:#eef0f5;border-radius:6px;padding:1px 7px;margin:0 6px;color:var(--mute)}
.tag.messy{background:#fff1d6;color:#8a5a00}
pre{background:#0f1626;color:#d7e0f5;padding:14px;border-radius:10px;overflow:auto;font-size:12.5px;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{border-bottom:1px solid var(--line);padding:8px 8px;text-align:left;vertical-align:top}
th{color:var(--mute);font-weight:600;font-size:12px;text-transform:uppercase}
.ok{color:var(--good);font-weight:650}.no{color:var(--bad);font-weight:650}
.bar{height:26px;border-radius:6px;color:#fff;font-weight:650;padding:2px 10px;margin:6px 0;min-width:40px}
.result{font-size:18px;font-weight:600;padding:12px 14px;background:#eef6ff;border-radius:10px;margin:8px 0}
.mute{color:var(--mute);font-size:13px}
.report h4{margin:18px 0 6px;font-size:15px}.report p,.report li{font-size:14.5px}
@media print{nav,header .badge,.noprint{display:none}section{display:none}section.on{display:block}body{background:#fff}}
@media(max-width:560px){.g2{grid-template-columns:1fr}}
</style></head><body>
<header><div><h1>TESS - Enterprise World Model</h1><div class="sub">Temporal knowledge graph + LLM reasoning over an evolving organization</div></div><span class="badge" id="mode"></span></header>
<nav id="nav"></nav>
<main>

<section id="overview">
 <div class="grid g4" id="stats"></div><br>
 <div class="card"><h3>How the system works</h3>
  <div class="flow">
   <div><b>1. Sources</b>Slack, email, calendar, meeting notes, documents</div><i>&rarr;</i>
   <div><b>2. LLM ingestion</b>Messy text becomes clean facts (who, what, when)</div><i>&rarr;</i>
   <div><b>3. Temporal graph</b>People, tasks, projects, documents, meetings. Every link has a start and end date</div><i>&rarr;</i>
   <div><b>4. Reasoning</b>Paths, impact, ownership and changes as of any date</div><i>&rarr;</i>
   <div><b>5. LLM answers</b>The LLM gets graph facts as context instead of loose documents</div>
  </div></div>
 <div class="card"><h3>Headline result</h3><div id="headline"></div></div>
 <div class="card"><h3>What to try</h3><ul>
  <li><b>Timeline</b>: drag the dates to watch ownership and status change.</li>
  <li><b>Ask TESS</b>: run relationship questions such as impact or connection paths.</li>
  <li><b>Messy text</b>: see how raw chat messages are turned into graph updates.</li>
  <li><b>Evaluation</b>: graph versus plain keyword search on 10 questions.</li>
  <li><b>Report</b>: ready-made write-up. Use Print to save it as PDF.</li></ul></div>
</section>

<section id="timeline">
 <div class="card"><div class="row">
  <div><label>Date A</label><br><input type="range" id="sA"> <span class="dt" id="dA"></span></div>
  <div><label>Date B</label><br><input type="range" id="sB"> <span class="dt" id="dB"></span></div>
  <button class="btn" id="preset">Reset to Sep 10 &rarr; Oct 10</button></div>
  <div class="mute">Red arrows on each side are ownership links that do not exist on the other date.</div></div>
 <div class="grid g2"><div><svg id="svgA"></svg></div><div><svg id="svgB"></svg></div></div>
 <div class="legend"><span><i style="background:#ef6f6c"></i>blocked</span><span><i style="background:#ffd166"></i>in progress</span><span><i style="background:#8fd694"></i>done</span><span><i style="background:#ddd"></i>no status yet</span></div><br>
 <div class="grid g2">
  <div class="card"><h3>What changed from A to B</h3><div id="diff"></div></div>
  <div class="card"><h3>Events that caused it</h3><div class="feed" id="feed"></div></div></div>
</section>

<section id="ask">
 <div class="card"><h3>Ask the world model</h3>
  <div class="row"><div><label>Question</label><br><select id="qType"></select></div>
   <div id="w1"><label id="l1"></label><br><select id="p1"></select></div>
   <div id="w2"><label>and</label><br><select id="p2"></select></div></div>
  <div class="row"><div><label>As of date</label><br><input type="range" id="sQ"> <span class="dt" id="dQ"></span></div>
   <button class="btn" id="run">Ask</button></div>
  <div id="answer"></div></div>
 <div class="card"><h3>What an LLM would receive</h3><div class="mute">Instead of searching documents, TESS hands the LLM the relevant sub-graph as of the chosen date.</div><pre id="prompt"></pre></div>
</section>

<section id="messy">
 <div class="card"><h3>Reading messy human messages</h3><div class="mute" id="messyNote"></div></div>
 <div id="messyList"></div>
</section>

<section id="evaluation">
 <div class="card"><h3>Graph vs. keyword search (10 questions)</h3><div id="bars"></div>
  <div class="mute">Search sees only messages up to the question date and may pick the top 3 matches. The graph answers from relationships and dates.</div></div>
 <div class="card"><table><thead><tr><th>#</th><th>Question</th><th>Correct answer</th><th>Graph</th><th>Search</th></tr></thead><tbody id="evalBody"></tbody></table></div>
</section>

<section id="report">
 <div class="card report" id="reportBody"></div>
 <button class="btn noprint" onclick="window.print()">Print / Save as PDF</button>
</section>
</main>

<script>
const D = __DATA__;
/* ======================= pure logic (mirrors pbl.py) ======================= */
const E = Object.fromEntries(D.entities.map(e => [e.id, e]));
const N = id => E[id] ? E[id].name : id;
const act = (e, d) => e.valid_from <= d && (e.valid_to === null || d < e.valid_to);
const attrAt = (id, k, d) => { let v = null; for (const [val, dt] of (E[id].attrs[k] || [])) if (dt <= d) v = val; return v; };
const outE = (id, d, rel) => D.edges.filter(e => e.src === id && act(e, d) && (!rel || e.rel === rel));
const inE  = (id, d, rel) => D.edges.filter(e => e.dst === id && act(e, d) && (!rel || e.rel === rel));
const owner = (t, d) => outE(t, d, 'assigned_to').map(e => e.dst);
const openWork = (p, d) => inE(p, d, 'assigned_to').map(e => e.src).filter(t => attrAt(t, 'status', d) !== 'done');
const attendees = (m, d) => inE(m, d, 'attended').map(e => e.src);
const blockedTasks = d => D.entities.filter(e => e.type === 'task' && attrAt(e.id, 'status', d) === 'blocked').map(e => e.id);
function impact(t, d) {
  const seen = new Set(), q = [t];
  while (q.length) { const c = q.shift(); for (const e of inE(c, d, 'depends_on')) if (!seen.has(e.src)) { seen.add(e.src); q.push(e.src); } }
  return [...seen];
}
function findPath(a, b, d) {
  if (a === b) return [];
  const prev = {[a]: null}, q = [a];
  while (q.length) {
    const cur = q.shift(); if (cur === b) break;
    for (const e of D.edges) {
      if (!act(e, d)) continue;
      let nxt; if (e.src === cur) nxt = e.dst; else if (e.dst === cur) nxt = e.src; else continue;
      if (!(nxt in prev)) { prev[nxt] = [cur, `${N(e.src)} --${e.rel}--> ${N(e.dst)}`]; q.push(nxt); }
    }
  }
  if (!(b in prev)) return null;
  const hops = []; let n = b; while (prev[n]) { hops.push(prev[n][1]); n = prev[n][0]; }
  return hops.reverse();
}
function snap(d) {
  const edges = new Set(D.edges.filter(e => act(e, d)).map(e => `${e.src}|${e.rel}|${e.dst}`));
  const attrs = {};
  for (const e of D.entities) for (const k of Object.keys(e.attrs)) attrs[`${e.id}|${k}`] = attrAt(e.id, k, d);
  return {edges, attrs};
}
function diff(a, b) {
  const A = snap(a), B = snap(b), out = [];
  for (const k of [...B.edges].sort()) if (!A.edges.has(k)) { const [s, r, t] = k.split('|'); out.push({t: 'add', s: `+ ${N(s)} --${r}--> ${N(t)}`}); }
  for (const k of [...A.edges].sort()) if (!B.edges.has(k)) { const [s, r, t] = k.split('|'); out.push({t: 'del', s: `- ${N(s)} --${r}--> ${N(t)}`}); }
  for (const k of Object.keys(B.attrs).sort()) if (A.attrs[k] !== B.attrs[k]) { const [i, key] = k.split('|'); out.push({t: 'mod', s: `~ ${N(i)}.${key}: ${A.attrs[k] === null ? 'none' : A.attrs[k]} -> ${B.attrs[k] === null ? 'none' : B.attrs[k]}`}); }
  return out;
}
function ctx(id, d, hops = 2) {
  const seen = new Set([id]); let frontier = [id]; const lines = [];
  const entLine = c => { const ent = E[c], at = {}; for (const k of Object.keys(ent.attrs)) { const v = attrAt(c, k, d); if (v !== null) at[k] = v; } return `${ent.type}:${ent.name} ${JSON.stringify(at)}`; };
  for (let h = 0; h < hops; h++) {
    const nxt = [];
    for (const cur of frontier) {
      lines.push(entLine(cur));
      for (const e of outE(cur, d)) { lines.push(`  ${N(e.src)} --${e.rel}--> ${N(e.dst)}`); if (!seen.has(e.dst)) { seen.add(e.dst); nxt.push(e.dst); } }
      for (const e of inE(cur, d)) if (!seen.has(e.src)) { seen.add(e.src); nxt.push(e.src); }
    }
    frontier = nxt;
  }
  for (const cur of frontier) lines.push(entLine(cur));
  return lines.join('\n');
}
function isoAdd(iso, n) { const [y, m, d] = iso.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10); }
/* ============================ UI ============================ */
const $ = s => document.querySelector(s);
const days = []; for (let d = D.minDate; d <= D.maxDate; d = isoAdd(d, 1)) days.push(d);
const nice = d => { const [y, m, dd] = d.split('-').map(Number); return new Date(Date.UTC(y, m - 1, dd)).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'}); };
const idxOf = d => Math.max(0, days.indexOf(d));
const names = ids => ids.length ? ids.map(N).join(', ') : '(none)';
const STATUS = {blocked: '#ef6f6c', in_progress: '#ffd166', done: '#8fd694', null: '#dddddd'};

$('#mode').textContent = 'LLM mode: ' + D.mode;
const TABS = [['overview', 'Overview'], ['timeline', 'Timeline'], ['ask', 'Ask TESS'], ['messy', 'Messy text'], ['evaluation', 'Evaluation'], ['report', 'Report']];
$('#nav').innerHTML = TABS.map(([id, l]) => `<button data-t="${id}">${l}</button>`).join('');
function showTab(id) { document.querySelectorAll('section').forEach(s => s.classList.toggle('on', s.id === id)); document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.t === id)); }
document.querySelectorAll('nav button').forEach(b => b.onclick = () => showTab(b.dataset.t));

/* ---- overview ---- */
const cnt = t => D.entities.filter(e => e.type === t).length;
const closed = D.edges.filter(e => e.valid_to !== null).length;
$('#stats').innerHTML = [[D.entities.length, 'entities'], [cnt('person'), 'people'], [D.edges.length, 'relationships'], [closed, 'relationships that ended'], [D.events.length, 'events ingested']]
  .map(([n, l]) => `<div class="card stat"><b>${n}</b><span>${l}</span></div>`).join('');
const ev = D.eval;
$('#headline').innerHTML = `<div class="bar" style="background:#1f9d55;width:${100 * ev.graph / ev.total}%">Graph ${ev.graph}/${ev.total}</div>
 <div class="bar" style="background:#d62828;width:${Math.max(8, 100 * ev.search / ev.total)}%">Keyword search ${ev.search}/${ev.total}</div>
 <p class="mute">Search fails whenever an answer depends on time (who owns it NOW?) or on several linked facts (what is affected if X slips?).</p>`;

/* ---- timeline ---- */
const people = D.entities.filter(e => e.type === 'person'), tasks = D.entities.filter(e => e.type === 'task');
const ownSet = d => new Set(D.edges.filter(e => e.rel === 'assigned_to' && act(e, d)).map(e => `${e.src}|${e.dst}`));
function drawOwn(svg, d, other, id) {
  const here = ownSet(d), oth = ownSet(other), step = 46, top = 44, h = top + step * (people.length - 1) + 36;
  const py = i => top + i * step, ty = i => top + i * (step * (people.length - 1) / (tasks.length - 1));
  const pi = Object.fromEntries(people.map((p, i) => [p.id, i])), ti = Object.fromEntries(tasks.map((t, i) => [t.id, i]));
  let s = `<defs>${[['g', '#7a7a7a'], ['r', '#d62828']].map(([k, c]) => `<marker id="m${k}${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="${c}"/></marker>`).join('')}</defs>`;
  s += `<text x="260" y="24" text-anchor="middle" font-size="16" font-weight="700" fill="#1d2433">${nice(d)}</text>`;
  for (const k of here) { const [t, p] = k.split('|'), isNew = !oth.has(k);
    s += `<line x1="300" y1="${ty(ti[t])}" x2="134" y2="${py(pi[p])}" stroke="${isNew ? '#d62828' : '#7a7a7a'}" stroke-width="${isNew ? 3 : 1.3}" marker-end="url(#m${isNew ? 'r' : 'g'}${id})"/>`; }
  people.forEach((p, i) => s += `<rect x="20" y="${py(i) - 15}" width="112" height="30" rx="7" fill="#f4a261" stroke="#555"/><text x="76" y="${py(i) + 5}" text-anchor="middle" font-size="13">${p.name}</text>`);
  tasks.forEach((t, i) => s += `<rect x="300" y="${ty(i) - 14}" width="200" height="28" rx="7" fill="${STATUS[attrAt(t.id, 'status', d)]}" stroke="#555"/><text x="400" y="${ty(i) + 5}" text-anchor="middle" font-size="12.5">${t.name}</text>`);
  svg.setAttribute('viewBox', `0 0 520 ${h}`); svg.innerHTML = s;
}
function renderTimeline() {
  const a = days[$('#sA').value], b = days[$('#sB').value];
  $('#dA').textContent = nice(a); $('#dB').textContent = nice(b);
  drawOwn($('#svgA'), a, b, 'A'); drawOwn($('#svgB'), b, a, 'B');
  const [lo, hi] = a <= b ? [a, b] : [b, a];
  const df = diff(lo, hi);
  $('#diff').innerHTML = df.length ? df.map(c => `<div class="chg ${c.t}">${c.s}</div>`).join('') : '<span class="mute">No change between these dates.</span>';
  const evs = D.events.filter(e => e.date > lo && e.date <= hi);
  $('#feed').innerHTML = evs.length ? evs.map(e => `<div><b>${e.date}</b><span class="tag ${e.source === 'messy' ? 'messy' : ''}">${e.source}</span>${e.text}${e.clean ? `<br><span class="mute">&rarr; ${e.clean}</span>` : ''}</div>`).join('') : '<span class="mute">No events in this range.</span>';
}
for (const id of ['#sA', '#sB', '#sQ']) { $(id).min = 0; $(id).max = days.length - 1; }
$('#sA').value = idxOf('2026-09-10'); $('#sB').value = days.length - 1; $('#sQ').value = days.length - 1;
$('#sA').oninput = $('#sB').oninput = renderTimeline;
$('#preset').onclick = () => { $('#sA').value = idxOf('2026-09-10'); $('#sB').value = days.length - 1; renderTimeline(); };

/* ---- ask ---- */
const QUERIES = [
  {id: 'owner', label: 'Who owns this task?', t1: 'task', l1: 'Task'},
  {id: 'open', label: 'What open work does this person have?', t1: 'person', l1: 'Person'},
  {id: 'impact', label: 'If this task slips, what is affected?', t1: 'task', l1: 'Task'},
  {id: 'path', label: 'How are these two things connected?', t1: 'any', l1: 'From', t2: 'any'},
  {id: 'blocked', label: 'Which tasks are blocked?'},
  {id: 'att', label: 'Who attended this meeting?', t1: 'meeting', l1: 'Meeting'},
  {id: 'disc', label: 'Who attended a meeting that discussed this document?', t1: 'document', l1: 'Document'},
];
const fill = (sel, type) => sel.innerHTML = D.entities.filter(e => type === 'any' || e.type === type).map(e => `<option value="${e.id}">${e.name}${type === 'any' ? ' (' + e.type + ')' : ''}</option>`).join('');
$('#qType').innerHTML = QUERIES.map((q, i) => `<option value="${i}">${q.label}</option>`).join('');
function setupQuery() {
  const q = QUERIES[$('#qType').value];
  $('#w1').style.display = q.t1 ? '' : 'none'; $('#w2').style.display = q.t2 ? '' : 'none';
  if (q.t1) { $('#l1').textContent = q.l1; fill($('#p1'), q.t1); }
  if (q.t2) { fill($('#p2'), q.t2); $('#p2').selectedIndex = Math.min(3, $('#p2').options.length - 1); }
  runAsk();
}
function runAsk() {
  const q = QUERIES[$('#qType').value], d = days[$('#sQ').value], a = $('#p1').value, b = $('#p2').value;
  $('#dQ').textContent = nice(d);
  let res = '', question = q.label, ctxIds = [];
  if (q.id === 'owner') { res = names(owner(a, d)); question = `Who owns ${N(a)}?`; ctxIds = [a]; }
  if (q.id === 'open') { res = names(openWork(a, d)); question = `What open work does ${N(a)} have?`; ctxIds = [a]; }
  if (q.id === 'impact') { res = names(impact(a, d)); question = `If ${N(a)} slips, what is affected?`; ctxIds = [a]; }
  if (q.id === 'blocked') { const bl = blockedTasks(d); res = names(bl); ctxIds = bl; }
  if (q.id === 'att') { res = names(attendees(a, d)); question = `Who attended ${N(a)}?`; ctxIds = [a]; }
  if (q.id === 'disc') { const ms = inE(a, d, 'discussed').map(e => e.src); res = names([...new Set(ms.flatMap(m => attendees(m, d)))]); question = `Who attended a meeting that discussed ${N(a)}?`; ctxIds = [a, ...ms]; }
  if (q.id === 'path') { const p = findPath(a, b, d); res = p === null ? 'No connection found on this date.' : p.length ? p.map(h => '&bull; ' + h).join('<br>') : 'Same entity.'; question = `How is ${N(a)} connected to ${N(b)}?`; ctxIds = [a, b]; }
  $('#answer').innerHTML = `<div class="result">${res}</div>`;
  const facts = ctxIds.length ? [...new Set(ctxIds)].map(i => ctx(i, d, 1)).join('\n') : '(no matching facts)';
  $('#prompt').textContent = `System: You are TESS. Answer ONLY from the graph facts. Reason about relationships and recent changes.\n\nFacts as of ${d}:\n${facts}\n\nQuestion: ${question}`;
}
$('#qType').onchange = setupQuery; $('#p1').onchange = $('#p2').onchange = $('#run').onclick = runAsk; $('#sQ').oninput = runAsk;

/* ---- messy text ---- */
$('#messyNote').textContent = D.mode.startsWith('ONLINE') ? 'Claude converts each message into simple sentences, which are then added to the graph.' : 'Offline mode: a small rule-based stand-in plays the LLM. Add an LLM API key (see README) to use a real model instead. The graph updates are identical.';
$('#messyList').innerHTML = D.events.filter(e => e.clean !== null).map(e => {
  const df = diff(isoAdd(e.date, -1), e.date);
  return `<div class="card"><div><b>${e.date}</b><span class="tag messy">raw message</span></div>
  <p style="font-size:17px;margin:8px 0">&ldquo;${e.text}&rdquo;</p>
  <div class="mute">Understood as:</div><div class="result" style="font-size:15px">${e.clean}</div>
  <div class="mute">What changed in the graph that day:</div>${df.map(c => `<div class="chg ${c.t}">${c.s}</div>`).join('') || '<div class="mute">nothing</div>'}</div>`; }).join('');

/* ---- evaluation ---- */
$('#bars').innerHTML = `<div class="bar" style="background:#1f9d55;width:${100 * ev.graph / ev.total}%">Graph: ${ev.graph}/${ev.total} correct</div>
 <div class="bar" style="background:#d62828;width:${Math.max(10, 100 * ev.search / ev.total)}%">Search: ${ev.search}/${ev.total} correct</div>`;
$('#evalBody').innerHTML = ev.rows.map(r => `<tr><td>${r.n}</td><td>${r.q}<div class="mute">as of ${r.date}</div></td><td>${r.truth.join(', ')}</td>
 <td class="${r.graph_ok ? 'ok' : 'no'}">${r.graph_ok ? '&#10003; ' : '&#10007; '}${r.graph.join(', ') || '(none)'}</td>
 <td class="${r.search_ok ? 'ok' : 'no'}">${r.search_ok ? '&#10003; ' : '&#10007; '}${r.search.join(', ') || '(none)'}${r.note ? `<div class="mute" style="font-weight:400">${r.note}</div>` : ''}</td></tr>`).join('');

/* ---- report ---- */
const fails = ev.rows.filter(r => !r.search_ok);
$('#reportBody').innerHTML = `
<h2 style="margin-top:0">Enterprise World Model for TESS</h2>
<h4>1. Problem</h4><p>Company information is spread across email, chat, calendars and documents, but decisions depend on <i>relationships</i> (who owns what, what depends on what) and on <i>history</i> (what changed, and when). Retrieving isolated documents loses both.</p>
<h4>2. Approach</h4><ul>
<li><b>Structured representation:</b> ${cnt('person')} people, ${cnt('project')} projects, ${cnt('task')} tasks, ${cnt('document')} documents and ${cnt('meeting')} meetings, joined by typed relationships (assigned to, depends on, attended, authored, about, discussed).</li>
<li><b>Temporal information:</b> every relationship has a start and end date, and every attribute (such as status) keeps its history. A reassignment closes the old link instead of overwriting it, so the model can answer questions "as of" any date and report what changed.</li>
<li><b>LLM ingestion:</b> messy messages are converted into simple sentences and then into graph updates (${D.events.filter(e => e.clean !== null).length} messy messages in the demo; mode: ${D.mode}).</li>
<li><b>LLM reasoning:</b> for a question, the relevant sub-graph is serialized and given to the LLM as context, so it reasons over relationships and changes rather than retrieved text.</li></ul>
<h4>3. Results</h4><p>On ${ev.total} hand-checked questions the graph answered <b>${ev.graph}/${ev.total}</b> correctly versus <b>${ev.search}/${ev.total}</b> for keyword search over the raw messages. Search was correct on questions whose answer sits in a single message and failed on ${fails.length} questions: ${fails.map(r => 'Q' + r.n).join(', ')}.</p>
<ul>${fails.filter(r => r.note).map(r => `<li><b>Q${r.n}</b> (${r.q}) &ndash; ${r.note}</li>`).join('')}</ul>
<h4>4. Limitations</h4><ul>
<li>The data is a small synthetic organization (${D.entities.length} entities, ${D.events.length} events).</li>
<li>The offline ingestion stand-in only handles a few phrasings; real messages need the LLM.</li>
<li>The search baseline is simple. A stronger baseline (an LLM reading retrieved text) should be run in online mode.</li>
<li>Conflicting or wrong facts are not yet detected, and entity names must be known in advance.</li></ul>
<h4>5. Future work</h4><ul>
<li>Run the evaluation with a real LLM on both sides and on a larger question set.</li>
<li>Automatic entity discovery and de-duplication (for example "Bob" vs "Robert").</li>
<li>Confidence scores and source tracking for each fact, and conflict detection.</li>
<li>Connectors to real tools (Slack, calendar, documents) and a graph database for scale.</li></ul>`;

renderTimeline(); setupQuery(); showTab('overview');
</script></body></html>"""


def main():
    data = collect()
    html = TEMPLATE.replace("__DATA__", json.dumps(data))
    out = Path(__file__).resolve().parent / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {out}")
    print(f"Graph {data['eval']['graph']}/{data['eval']['total']}  |  "
          f"Search {data['eval']['search']}/{data['eval']['total']}")
    webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
