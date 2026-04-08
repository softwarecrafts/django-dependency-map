"""
dependency_map.renderer
~~~~~~~~~~~~~~~~~~~~~~~
Turns the unified graph dict from analyzer.py into a self-contained
interactive HTML file using D3 v7 force simulation.
"""
from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Edge colour scheme (matches legend in HTML)
# ---------------------------------------------------------------------------
COUPLING_COLORS = {
    "fk": "#3b82f6",        # blue   – FK/M2M only
    "import": "#10b981",    # green  – import only
    "both": "#a855f7",      # purple – import + FK (strong coupling)
    "violation": "#ef4444", # red    – import-linter violation
}


def render_html(
    graph: dict,
    title: str = "Django Dependency Map",
    refresh_url: str = "",
    version_url: str = "",
    highlight_apps: list[str] | None = None,
) -> str:
    """Return a self-contained HTML string visualising *graph*."""
    import json as _json
    graph_json  = json.dumps(graph, indent=2)
    colors_json = json.dumps(COUPLING_COLORS)
    highlight_json = _json.dumps(highlight_apps or [])

    return (
        _HTML_TEMPLATE
        .replace("__TITLE__", title)
        .replace("__GRAPH_JSON__", graph_json)
        .replace("__COLORS_JSON__", colors_json)
        .replace("__REFRESH_URL__", refresh_url)
        .replace("__VERSION_URL__", version_url)
        .replace("__HIGHLIGHT_APPS__", highlight_json)
    )


def write_html(
    graph: dict,
    output_path: str | Path,
    title: str = "Django Dependency Map",
    refresh_url: str = "",
    highlight_apps: list[str] | None = None,
):
    html = render_html(graph, title, refresh_url=refresh_url, highlight_apps=highlight_apps)
    Path(output_path).write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML template — everything is embedded, zero external runtime deps
# (D3 loaded from cdnjs, Google Fonts loaded from fonts.googleapis.com)
# ---------------------------------------------------------------------------
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&family=Space+Grotesk:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:       #07090f;
  --surface:  #0d1117;
  --border:   #1e2533;
  --text:     #c9d1d9;
  --muted:    #586069;
  --accent:   #58a6ff;
  --fk:       #3b82f6;
  --import:   #10b981;
  --both:     #a855f7;
  --violation:#ef4444;
  --node-bg:  #161b22;
  --node-ring:#2d3748;
  --font-mono: 'JetBrains Mono', monospace;
  --font-ui:   'Space Grotesk', sans-serif;
}

html, body {
  width: 100%; height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-ui);
  overflow: hidden;
}

/* ── Layout ────────────────────────────────────────────────── */
#shell {
  display: grid;
  grid-template-columns: 180px 1fr 300px;
  grid-template-rows: 48px 1fr;
  height: 100vh;
}

/* ── Top bar ────────────────────────────────────────────────── */
#topbar {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  z-index: 10;
}

#topbar h1 {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--accent);
  letter-spacing: .05em;
  white-space: nowrap;
}

.stat-pill {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  white-space: nowrap;
}
.stat-pill span { color: var(--text); font-weight: 600; }

.filter-group {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.filter-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  border: 1px solid;
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  background: transparent;
  opacity: 0.45;
  transition: opacity .15s, background .15s;
}
.filter-btn.active { opacity: 1; }
.filter-btn:hover  { opacity: .8; }
.filter-btn[data-type="fk"]        { color: var(--fk);        border-color: var(--fk);        }
.filter-btn[data-type="import"]    { color: var(--import);    border-color: var(--import);    }
.filter-btn[data-type="both"]      { color: var(--both);      border-color: var(--both);      }
.filter-btn[data-type="violation"] { color: var(--violation); border-color: var(--violation); }
.filter-btn[data-type="cycle"]     { color: #f97316;          border-color: #f97316;          }
.filter-btn[data-type="fk"].active        { background: rgba(59,130,246,.15); }
.filter-btn[data-type="import"].active    { background: rgba(16,185,129,.15); }
.filter-btn[data-type="both"].active      { background: rgba(168,85,247,.15); }
.filter-btn[data-type="violation"].active { background: rgba(239,68,68,.15);  }
.filter-btn[data-type="cycle"].active     { background: rgba(249,115,22,.15); }

.layout-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  background: transparent;
  color: var(--muted);
  opacity: 0.5;
  transition: opacity .15s, color .15s;
}
.layout-btn.active { opacity: 1; color: var(--text); border-color: var(--accent); }
.layout-btn:hover  { opacity: .8; }

.refresh-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 12px;
  cursor: pointer;
  background: transparent;
  color: var(--muted);
  margin-left: 4px;
  transition: color .15s, border-color .15s;
}
.refresh-btn:hover:not(:disabled) { color: var(--text); border-color: var(--accent); }
.refresh-btn:disabled { opacity: 0.4; cursor: default; }

/* ── Canvas ─────────────────────────────────────────────────── */
#canvas {
  position: relative;
  overflow: hidden;
  background: var(--bg);
  background-image:
    radial-gradient(circle at 20% 30%, rgba(59,130,246,.04) 0%, transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(168,85,247,.04) 0%, transparent 50%);
}

#canvas svg {
  width: 100%;
  height: 100%;
  cursor: grab;
}
#canvas svg:active { cursor: grabbing; }

/* dot grid */
#canvas::before {
  content: '';
  position: absolute; inset: 0;
  background-image: radial-gradient(circle, rgba(255,255,255,.06) 1px, transparent 1px);
  background-size: 28px 28px;
  pointer-events: none;
}

/* ── Nodes ───────────────────────────────────────────────────── */
.node { cursor: pointer; }
.node circle {
  stroke-width: 1.5px;
  transition: filter .2s;
}
.node:hover circle { filter: brightness(1.3); }
.node.dimmed circle { opacity: 0.15; }
.node.dimmed text   { opacity: 0.1; }
.node.highlighted circle { filter: brightness(1.4) drop-shadow(0 0 8px currentColor); }

.node text {
  font-family: var(--font-mono);
  font-size: 11px;
  fill: var(--text);
  text-anchor: middle;
  dominant-baseline: central;
  pointer-events: none;
  font-weight: 500;
}
.node .model-count {
  font-size: 9px;
  fill: var(--muted);
}

/* ── Edges ───────────────────────────────────────────────────── */
.link {
  fill: none;
  stroke-width: 1.5;
  transition: opacity .2s;
}
.link.dimmed { opacity: 0.04; }
.link.highlighted { stroke-width: 2.5; }
.link[data-coupling="both"] { stroke-width: 2px; }
.link[data-coupling="violation"] { stroke-width: 2.5px; }

/* ── Side panel ─────────────────────────────────────────────── */
#panel {
  background: var(--surface);
  border-left: 1px solid var(--border);
  overflow-y: auto;
  padding: 0;
}

#panel-header {
  padding: 14px 16px 12px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--surface);
  z-index: 1;
}
#panel-header h2 {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
  font-weight: 500;
  margin-bottom: 2px;
  letter-spacing: .04em;
}
#panel-header p {
  font-size: 11px;
  color: var(--muted);
}

.panel-section {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.panel-section h3 {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--muted);
  letter-spacing: .08em;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.model-chip {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 2px 6px;
  margin: 2px 2px 2px 0;
  color: var(--text);
}

.dep-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 11px;
  font-family: var(--font-mono);
}
.dep-row .dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dep-row .app-name { color: var(--text); }
.dep-row .coupling-label {
  font-size: 9px;
  color: var(--muted);
  margin-left: auto;
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 5px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
  font-size: 11px;
}
.metric-row .label { color: var(--muted); font-family: var(--font-mono); }
.metric-row .value { color: var(--text); font-weight: 600; font-family: var(--font-mono); }


/* ── App list sidebar ────────────────────────────────────────── */
#app-list {
  background: var(--surface);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

#app-list-header {
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--surface);
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
#app-list-header h2 {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--muted);
  letter-spacing: .08em;
  text-transform: uppercase;
  flex: 1;
}
.app-list-action {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  transition: color .15s;
}
.app-list-action:hover { color: var(--text); }

.app-list-search {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 37px;
  background: var(--surface);
  z-index: 1;
}
.app-list-search input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 4px 8px;
  outline: none;
}
.app-list-search input:focus { border-color: var(--accent); }
.app-list-search input::placeholder { color: var(--muted); }

#app-list-items {
  flex: 1;
  padding: 4px 0;
}

.app-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  cursor: pointer;
  transition: background .1s;
  user-select: none;
}
.app-item:hover { background: rgba(255,255,255,.03); }
.app-item.hidden-app { opacity: 0.3; }

.app-item-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 1px solid;
  transition: background .15s;
}
.app-item.hidden-app .app-item-dot { background: transparent !important; }

.app-item-name {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-item-count {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--muted);
}

/* ── Tooltip ─────────────────────────────────────────────────── */
#tooltip {
  position: fixed;
  pointer-events: none;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 11px;
  font-family: var(--font-mono);
  max-width: 280px;
  z-index: 100;
  opacity: 0;
  transition: opacity .1s;
  box-shadow: 0 8px 32px rgba(0,0,0,.6);
}
#tooltip.visible { opacity: 1; }
#tooltip .tt-title {
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
  font-size: 12px;
}
#tooltip .tt-row {
  color: var(--muted);
  line-height: 1.6;
}
#tooltip .tt-row strong { color: var(--text); }

/* ── Empty state ─────────────────────────────────────────────── */
#empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 13px;
  gap: 8px;
  display: none;
}

.no-grimp-banner {
  background: rgba(168,85,247,.1);
  border: 1px solid rgba(168,85,247,.3);
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 11px;
  color: #c084fc;
  font-family: var(--font-mono);
  margin: 12px 16px;
  line-height: 1.6;
}
</style>
</head>
<body>
<div id="shell">
  <!-- Top bar -->
  <div id="topbar">
    <h1>⬡ __TITLE__</h1>
    <div class="stat-pill" id="stat-apps">apps <span>—</span></div>
    <div class="stat-pill" id="stat-edges">edges <span>—</span></div>
    <div class="stat-pill" id="stat-violations" style="display:none">violations <span style="color:var(--violation)">—</span></div>
    <div class="stat-pill" id="stat-cycles" style="display:none">cycles <span style="color:#f97316">—</span></div>
    <div class="filter-group">
      <button class="filter-btn active" data-type="fk">FK</button>
      <button class="filter-btn active" data-type="import">import</button>
      <button class="filter-btn active" data-type="both">both</button>
      <button class="filter-btn active" data-type="violation">violation</button>
      <button class="filter-btn active" data-type="cycle" style="color:#f97316;border-color:#f97316">cycles</button>
    </div>
    <div style="display:flex;gap:6px;margin-left:8px">
      <button class="layout-btn active" data-layout="force" title="Force-directed layout">force</button>
      <button class="layout-btn" data-layout="hierarchy" title="Hierarchical (dagre) layout">hierarchy</button>
    </div>
    <button id="refresh-btn" class="refresh-btn" style="display:none" title="Re-run analysis">↻ refresh</button>
    <button id="export-btn" class="refresh-btn" title="Export visible graph (Mermaid / DOT)">⬡ export</button>
  </div>

  <!-- App list sidebar -->
  <div id="app-list">
    <div id="app-list-header">
      <h2>Apps</h2>
      <button class="app-list-action" id="btn-show-all" title="Show all">all</button>
      <button class="app-list-action" id="btn-hide-all" title="Hide all">none</button>
      <button class="app-list-action" id="btn-hide-3p" title="Toggle third-party apps (allauth, django.contrib, etc.)">3P</button>
    </div>
    <div class="app-list-search">
      <input type="text" id="app-search" placeholder="filter…" autocomplete="off">
    </div>
    <div id="app-list-items"></div>
  </div>

  <!-- Graph canvas -->
  <div id="canvas">
    <svg id="svg"></svg>
    <div id="empty">No apps found.<br>Check that graph_models is installed and run from your project root.</div>
  </div>

  <!-- Side panel -->
  <div id="panel">
    <div id="panel-header">
      <h2 id="panel-title">SELECT AN APP</h2>
      <p id="panel-subtitle">Click any node to inspect</p>
    </div>
    <div id="panel-body"></div>
  </div>
</div>

<!-- Export modal -->
<div id="export-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;align-items:center;justify-content:center;">
  <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;width:680px;max-width:95vw;max-height:85vh;display:flex;flex-direction:column;overflow:hidden;">
    <div style="padding:14px 18px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;">
      <span style="font-family:var(--font-mono);font-size:13px;color:var(--accent);font-weight:500">Export visible graph</span>
      <div style="margin-left:auto;display:flex;gap:6px;">
        <button id="export-tab-mermaid" class="layout-btn active" style="font-size:10px;padding:2px 8px">Mermaid</button>
        <button id="export-tab-dot"     class="layout-btn"        style="font-size:10px;padding:2px 8px">DOT</button>
      </div>
      <button id="export-copy" class="refresh-btn" style="margin-left:8px">copy</button>
      <button id="export-close" style="background:none;border:none;color:var(--muted);font-size:18px;cursor:pointer;line-height:1;padding:0 4px">×</button>
    </div>
    <div style="padding:6px 12px 4px;border-bottom:1px solid var(--border);">
      <span style="font-family:var(--font-mono);font-size:10px;color:var(--muted)" id="export-subtitle"></span>
    </div>
    <pre id="export-content" style="flex:1;overflow:auto;margin:0;padding:16px;font-family:var(--font-mono);font-size:11px;color:var(--text);background:var(--bg);white-space:pre;"></pre>
  </div>
</div>

<div id="tooltip"></div>

<script>
// ══ CONSTANTS ════════════════════════════════════════════════════════════════
const COLORS         = __COLORS_JSON__;
const CYCLE_COLOR    = '#f97316';
const FK_CYCLE_COLOR = '#eab308';
const REFRESH_URL    = '__REFRESH_URL__';
const VERSION_URL    = '__VERSION_URL__';
const HIGHLIGHT_APPS = __HIGHLIGHT_APPS__;   // [] or ['billing','users']

// ══ MUTABLE GRAPH STATE ══════════════════════════════════════════════════════
let FULL_GRAPH;                          // source of truth — never filtered
let apps, edges, stats, cycles, directImportCycles, directFkCycles;
let nodes, links, nodeEls, linkEls, sim;
let maxModels = 1;
let selected  = null;

// ══ PERSISTENT UI STATE ═══════════════════════════════════════════════════════
const activeFilters = new Set(['fk', 'import', 'both', 'violation', 'cycle']);
const hiddenApps    = new Set();
let   currentLayout = 'force';

// Debounce handle for subgraph rebuild
let _rebuildTimer = null;

// ══ HELPERS ═══════════════════════════════════════════════════════════════════
const nodeR = a => 18 + (a.model_count / maxModels) * 24;
const w = () => document.getElementById('canvas').clientWidth;
const h = () => document.getElementById('canvas').clientHeight;

function isEdgeVisible(e) {
  if ((e.in_import_cycle || e.in_fk_cycle) && !activeFilters.has('cycle')) return false;
  return activeFilters.has(e.violation ? 'violation' : e.coupling);
}

// ══ ONE-TIME SVG SETUP ════════════════════════════════════════════════════════
const svg  = d3.select('#svg');
const g    = svg.append('g');
const zoom = d3.zoom().scaleExtent([0.15, 4]).on('zoom', e => g.attr('transform', e.transform));
svg.call(zoom);
const defs = svg.append('defs');

const filt = defs.append('filter').attr('id', 'glow');
filt.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'coloredBlur');
const merge = filt.append('feMerge');
merge.append('feMergeNode').attr('in', 'coloredBlur');
merge.append('feMergeNode').attr('in', 'SourceGraphic');

function buildMarkers() {
  defs.selectAll('marker').remove();
  Object.entries(COLORS).forEach(([type, color]) => {
    defs.append('marker').attr('id', `arrow-${type}`)
      .attr('viewBox','0 -5 10 10').attr('refX',10).attr('refY',0)
      .attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto')
      .append('path').attr('d','M0,-5L10,0L0,5').attr('fill',color).attr('opacity',0.8);
  });
  ['cycle','fk-cycle'].forEach((id, i) => {
    defs.append('marker').attr('id', `arrow-${id}`)
      .attr('viewBox','0 -5 10 10').attr('refX',10).attr('refY',0)
      .attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto')
      .append('path').attr('d','M0,-5L10,0L0,5')
      .attr('fill', i===0 ? CYCLE_COLOR : FK_CYCLE_COLOR).attr('opacity',0.8);
  });
}
buildMarkers();

// ══ LIVE SUBGRAPH COMPUTATION ═════════════════════════════════════════════════
// Tarjan's SCC — identical logic to cycles.py, ported to JS
function tarjanSCCs(edges, edgeType) {
  const adj = {}, allNodes = new Set();
  edges.forEach(e => {
    allNodes.add(e.source); allNodes.add(e.target);
    if (e.types.includes(edgeType)) {
      if (!adj[e.source]) adj[e.source] = [];
      adj[e.source].push(e.target);
    }
  });

  let counter = 0;
  const idx = {}, low = {}, onStack = {}, stack = [], sccs = [];

  function visit(v) {
    idx[v] = low[v] = counter++;
    stack.push(v); onStack[v] = true;
    for (const w of (adj[v] || [])) {
      if (idx[w] === undefined) { visit(w); low[v] = Math.min(low[v], low[w]); }
      else if (onStack[w])      { low[v] = Math.min(low[v], idx[w]); }
    }
    if (low[v] === idx[v]) {
      const scc = [];
      let w; do { w = stack.pop(); onStack[w] = false; scc.push(w); } while (w !== v);
      if (scc.length > 1) sccs.push(scc);
    }
  }
  [...allNodes].sort().forEach(n => { if (idx[n] === undefined) visit(n); });
  return sccs;
}

// BFS shortest cycle starting from `start` through real edges within `appSet`
function bfsShortestCycle(start, adj, appSet) {
  const queue = [[start, [start]]];
  while (queue.length) {
    const [node, path] = queue.shift();
    if (path.length > appSet.size + 1) break;
    for (const nxt of ([...( adj[node] || [])].sort())) {
      if (!appSet.has(nxt)) continue;
      if (nxt === start && path.length > 1) return path;
      if (!path.includes(nxt)) queue.push([nxt, [...path, nxt]]);
    }
  }
  return [];
}

// Direct mutual pairs: both A→B and B→A exist
function findDirectCycles(edges, edgeType) {
  const fwd = new Set(edges.filter(e => e.types.includes(edgeType)).map(e => `${e.source}|${e.target}`));
  const pairs = new Set();
  edges.forEach(e => {
    if (e.types.includes(edgeType) && fwd.has(`${e.target}|${e.source}`)) {
      pairs.add([e.source, e.target].sort().join('|'));
    }
  });
  return [...pairs].sort().map(p => {
    const [a, b] = p.split('|');
    return { a, b, label: `${a} ↔ ${b}` };
  });
}

// Annotate a graph with cycle membership, metrics, direct pairs, stats
function annotateSubgraph(graph) {
  const edges = graph.edges;
  const impSCCs = tarjanSCCs(edges, 'import');
  const fkSCCs  = tarjanSCCs(edges, 'fk');

  const impMap = {}, fkMap = {};
  impSCCs.forEach((scc, i) => scc.forEach(a => impMap[a] = i));
  fkSCCs.forEach( (scc, i) => scc.forEach(a => fkMap[a]  = i));

  // Annotate apps
  const inDeg = {}, outDeg = {};
  edges.forEach(e => {
    outDeg[e.source] = (outDeg[e.source] || 0) + 1;
    inDeg[e.target]  = (inDeg[e.target]  || 0) + 1;
  });
  Object.keys(graph.apps).forEach(name => {
    const imp = impMap[name] !== undefined ? impMap[name] : -1;
    const fk  = fkMap[name]  !== undefined ? fkMap[name]  : -1;
    graph.apps[name] = {
      ...graph.apps[name],
      in_degree:          inDeg[name]  || 0,
      out_degree:         outDeg[name] || 0,
      in_import_cycle:    imp >= 0,
      import_cycle_index: imp,
      in_fk_cycle:        fk  >= 0,
      fk_cycle_index:     fk,
      in_cycle:           imp >= 0 || fk >= 0,
      cycle_index:        imp >= 0 ? imp : fk,
    };
  });

  // Annotate edges
  edges.forEach(e => {
    const si = impMap[e.source], ti = impMap[e.target];
    const sf = fkMap[e.source],  tf = fkMap[e.target];
    const imc = si !== undefined && si === ti && e.types.includes('import');
    const fkc = sf !== undefined && sf === tf && e.types.includes('fk');
    e.in_import_cycle = imc;
    e.in_fk_cycle     = fkc;
    e.in_cycle        = imc || fkc;
    e.cycle_index     = imc ? si : fkc ? sf : -1;
  });

  // Build adjacency for BFS
  const adjImp = {}, adjFk = {};
  edges.forEach(e => {
    if (e.types.includes('import')) { if (!adjImp[e.source]) adjImp[e.source]=[]; adjImp[e.source].push(e.target); }
    if (e.types.includes('fk'))     { if (!adjFk[e.source])  adjFk[e.source]=[];  adjFk[e.source].push(e.target); }
  });

  graph.cycles = [
    ...impSCCs.map(scc => {
      const s = new Set(scc), start = [...scc].sort()[0];
      const ex = bfsShortestCycle(start, adjImp, s);
      return { apps: scc, kind: 'import',
               label: scc.length === 2 ? `${scc[0]} ↔ ${scc[1]}` : `SCC of ${scc.length} apps: ${[...scc].sort().join(', ')}`,
               example_path: ex.length ? [...ex, ex[0]].join(' → ') : '' };
    }),
    ...fkSCCs.map(scc => {
      const s = new Set(scc), start = [...scc].sort()[0];
      const ex = bfsShortestCycle(start, adjFk, s);
      return { apps: scc, kind: 'fk',
               label: scc.length === 2 ? `${scc[0]} ↔ ${scc[1]}` : `SCC of ${scc.length} apps: ${[...scc].sort().join(', ')}`,
               example_path: ex.length ? [...ex, ex[0]].join(' → ') : '' };
    }),
  ];
  graph.direct_import_cycles = findDirectCycles(edges, 'import');
  graph.direct_fk_cycles     = findDirectCycles(edges, 'fk');

  const allCycleApps = new Set([...impSCCs.flat(), ...fkSCCs.flat()]);
  const n = Object.keys(graph.apps).length;
  graph.stats = {
    ...graph.stats,
    app_count:                  n,
    edge_count:                 edges.length,
    cycle_count:                impSCCs.length + fkSCCs.length,
    import_cycle_count:         impSCCs.length,
    fk_cycle_count:             fkSCCs.length,
    direct_import_cycle_count:  graph.direct_import_cycles.length,
    direct_fk_cycle_count:      graph.direct_fk_cycles.length,
    cyclic_app_count:           allCycleApps.size,
    violation_count:            edges.filter(e => e.violation).length,
    import_only_count:          edges.filter(e => e.coupling === 'import').length,
    fk_only_count:              edges.filter(e => e.coupling === 'fk').length,
    both_count:                 edges.filter(e => e.coupling === 'both').length,
  };
}

// Compute a visible subgraph from FULL_GRAPH, excluding hiddenApps
function computeSubgraph(hiddenSet) {
  if (hiddenSet.size === 0) {
    // Fast path: return a deep copy of the full graph
    const g = JSON.parse(JSON.stringify(FULL_GRAPH));
    annotateSubgraph(g);
    return g;
  }

  const filteredApps = Object.fromEntries(
    Object.entries(FULL_GRAPH.apps).filter(([name]) => !hiddenSet.has(name))
  );
  const filteredEdges = FULL_GRAPH.edges
    .filter(e => !hiddenSet.has(e.source) && !hiddenSet.has(e.target))
    .map(e => ({ ...e }));

  const subgraph = {
    apps:   filteredApps,
    edges:  filteredEdges,
    cycles: [],
    direct_import_cycles: [],
    direct_fk_cycles:     [],
    stats:  { ...FULL_GRAPH.stats },
  };
  annotateSubgraph(subgraph);
  return subgraph;
}

// ══ FILTER BUTTONS ════════════════════════════════════════════════════════════
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const t = btn.dataset.type;
    activeFilters.has(t) ? (activeFilters.delete(t), btn.classList.remove('active'))
                         : (activeFilters.add(t),    btn.classList.add('active'));
    updateVisibility();
  });
});

// ══ LAYOUT BUTTONS ════════════════════════════════════════════════════════════
document.querySelectorAll('.layout-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const layout = btn.dataset.layout;
    if (layout === currentLayout) return;
    currentLayout = layout;
    document.querySelectorAll('.layout-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.layout === layout));
    layout === 'hierarchy' ? applyDagreLayout() : applyForceLayout();
  });
});

// ══ REFRESH BUTTON ════════════════════════════════════════════════════════════
if (REFRESH_URL) document.getElementById('refresh-btn').style.display = '';
document.getElementById('refresh-btn').addEventListener('click', refreshGraph);

// ══ STATS UPDATE ══════════════════════════════════════════════════════════════
function updateStats() {
  document.querySelector('#stat-apps span').textContent  = stats.app_count;
  document.querySelector('#stat-edges span').textContent = stats.edge_count;

  const vEl = document.getElementById('stat-violations');
  if (stats.violation_count > 0) { vEl.style.display=''; vEl.querySelector('span').textContent=stats.violation_count; }
  else vEl.style.display = 'none';

  const cEl = document.getElementById('stat-cycles');
  if (stats.cycle_count > 0) {
    cEl.style.display = '';
    const parts=[];
    if (stats.import_cycle_count>0) parts.push(`${stats.import_cycle_count} import`);
    if (stats.fk_cycle_count>0)     parts.push(`${stats.fk_cycle_count} FK`);
    cEl.querySelector('span').textContent = parts.join(', ') || stats.cycle_count;
  } else cEl.style.display = 'none';

  document.getElementById('empty').style.display = apps.length===0 ? 'flex' : 'none';
}

// ══ EDGE PATH ═════════════════════════════════════════════════════════════════
function edgePath(d) {
  const sx=typeof d.source==='object'?d.source.x:d.source, sy=typeof d.source==='object'?d.source.y:d.source;
  const tx=typeof d.target==='object'?d.target.x:d.target, ty=typeof d.target==='object'?d.target.y:d.target;
  const dx=tx-sx, dy=ty-sy, dist=Math.sqrt(dx*dx+dy*dy)||1;
  const tr=nodeR(typeof d.target==='object'?d.target:{model_count:0});
  const ex=tx-(dx/dist)*(tr+8), ey=ty-(dy/dist)*(tr+8);
  const curve=currentLayout==='hierarchy'?0:30;
  return `M${sx},${sy} Q${(sx+ex)/2-dy/dist*curve},${(sy+ey)/2+dx/dist*curve} ${ex},${ey}`;
}

function nodeStrokeColor(d) {
  const out = edges.filter(e=>e.source===d.name);
  if (out.some(e=>e.violation))             return COLORS.violation;
  if (d.in_import_cycle)                    return CYCLE_COLOR;
  if (d.in_fk_cycle)                        return FK_CYCLE_COLOR;
  if (out.some(e=>e.coupling==='both'))     return COLORS.both;
  if (out.some(e=>e.coupling==='import'))   return COLORS.import;
  if (out.some(e=>e.coupling==='fk'))       return COLORS.fk;
  return '#2d3748';
}

// ══ BUILD LINKS ═══════════════════════════════════════════════════════════════
function buildLinks() {
  const tooltip = document.getElementById('tooltip');
  linkEls = g.append('g').attr('class','links').selectAll('path').data(links).join('path')
    .attr('class','link')
    .attr('data-coupling', d=>d.violation?'violation':d.coupling)
    .attr('stroke', d=>{
      if (d.violation)       return COLORS.violation;
      if (d.in_import_cycle) return CYCLE_COLOR;
      if (d.in_fk_cycle)     return FK_CYCLE_COLOR;
      return COLORS[d.coupling];
    })
    .attr('stroke-opacity', d=>d.coupling==='both'?0.85:0.6)
    .attr('stroke-dasharray', d=>d.coupling==='import'&&!d.in_import_cycle?'5,3':null)
    .attr('fill','none')
    .attr('stroke-width', d=>d.coupling==='both'||d.violation?2:1.5)
    .attr('marker-end', d=>{
      if (d.in_import_cycle) return 'url(#arrow-cycle)';
      if (d.in_fk_cycle)     return 'url(#arrow-fk-cycle)';
      if (d.violation)       return 'url(#arrow-violation)';
      return `url(#arrow-${d.coupling})`;
    })
    .on('mousemove', (event,d)=>{
      const s=typeof d.source==='object'?d.source.id:d.source;
      const t=typeof d.target==='object'?d.target.id:d.target;
      let html=`<div class="tt-title">${s} → ${t}</div>`;
      html+=`<div class="tt-row">type: <strong>${d.types.join(' + ')}</strong></div>`;
      if (d.in_import_cycle) html+=`<div class="tt-row" style="color:${CYCLE_COLOR}">⟳ import cycle</div>`;
      if (d.in_fk_cycle)     html+=`<div class="tt-row" style="color:${FK_CYCLE_COLOR}">⟳ FK cycle</div>`;
      if (d.violation)       html+=`<div class="tt-row" style="color:var(--violation)">⚠ violation</div>`;
      if (d.model_edges.length) {
        html+=`<div class="tt-row" style="margin-top:6px;color:var(--muted)">FK / M2M:</div>`;
        d.model_edges.slice(0,5).forEach(me=>{ html+=`<div class="tt-row">&nbsp;&nbsp;${me.from} → ${me.to}${me.label?` <span style="color:var(--muted)">(${me.label})</span>`:''}</div>`; });
        if (d.model_edges.length>5) html+=`<div class="tt-row" style="color:var(--muted)">+${d.model_edges.length-5} more</div>`;
      }
      tooltip.innerHTML=html; tooltip.classList.add('visible');
      tooltip.style.left=(event.clientX+14)+'px'; tooltip.style.top=(event.clientY-10)+'px';
    })
    .on('mousemove.move', ev=>{ tooltip.style.left=(ev.clientX+14)+'px'; tooltip.style.top=(ev.clientY-10)+'px'; })
    .on('mouseleave', ()=>tooltip.classList.remove('visible'));
}

// ══ BUILD NODES ═══════════════════════════════════════════════════════════════
function buildNodes() {
  nodeEls = g.append('g').attr('class','nodes').selectAll('g').data(nodes).join('g')
    .attr('class','node')
    .call(d3.drag()
      .on('start',(e,d)=>{ if(!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
      .on('drag', (e,d)=>{ d.fx=e.x; d.fy=e.y; })
      .on('end',  (e,d)=>{ if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }));

  nodeEls.append('circle').attr('r',nodeR).attr('fill','#0d1117')
    .attr('stroke',nodeStrokeColor).attr('stroke-width',1.5);
  nodeEls.append('circle').attr('r',d=>nodeR(d)-5).attr('fill','none')
    .attr('stroke',nodeStrokeColor).attr('stroke-width',0.5).attr('stroke-opacity',0.2);

  nodeEls.filter(d=>d.in_import_cycle).append('circle')
    .attr('r',d=>nodeR(d)+6).attr('fill','none')
    .attr('stroke',CYCLE_COLOR).attr('stroke-width',1).attr('stroke-dasharray','4,3').attr('stroke-opacity',0.7);
  nodeEls.filter(d=>d.in_fk_cycle).append('circle')
    .attr('r',d=>nodeR(d)+(d.in_import_cycle?12:6)).attr('fill','none')
    .attr('stroke',FK_CYCLE_COLOR).attr('stroke-width',1).attr('stroke-dasharray','2,4').attr('stroke-opacity',0.6);

  nodeEls.append('text').attr('dy',d=>d.model_count>0?'-5':'0')
    .style('font-family','var(--font-mono)').style('font-size','11px')
    .style('fill','var(--text)').style('text-anchor','middle')
    .style('dominant-baseline','central').style('pointer-events','none').style('font-weight','500')
    .text(d=>d.name);
  nodeEls.filter(d=>d.model_count>0).append('text').attr('dy','10')
    .style('font-family','var(--font-mono)').style('font-size','9px')
    .style('fill','var(--muted)').style('text-anchor','middle')
    .style('dominant-baseline','central').style('pointer-events','none')
    .text(d=>`${d.model_count} model${d.model_count!==1?'s':''}`);

  nodeEls.on('click',(event,d)=>{
    event.stopPropagation();
    selected = selected===d.id ? null : d.id;
    applySelection();
    renderPanel(selected ? apps.find(a=>a.name===selected) : null);
  });
  svg.on('click',()=>{ selected=null; applySelection(); renderPanel(null); });
}

// ══ BUILD SIMULATION ══════════════════════════════════════════════════════════
function buildSimulation() {
  sim = d3.forceSimulation(nodes)
    .force('link',    d3.forceLink(links).id(d=>d.id).distance(d=>d.coupling==='both'?130:180).strength(0.4))
    .force('charge',  d3.forceManyBody().strength(-500))
    .force('center',  d3.forceCenter(w()/2, h()/2))
    .force('collide', d3.forceCollide().radius(d=>nodeR(d)+20));
  sim.on('tick',()=>{ linkEls.attr('d',edgePath); nodeEls.attr('transform',d=>`translate(${d.x},${d.y})`); });
}

// ══ SELECTION ═════════════════════════════════════════════════════════════════
function applySelection() {
  if (!selected) { nodeEls.classed('dimmed',false).classed('highlighted',false); linkEls.classed('dimmed',false).classed('highlighted',false); return; }
  const conn=new Set([selected]);
  links.forEach(e=>{
    const s=typeof e.source==='object'?e.source.id:e.source, t=typeof e.target==='object'?e.target.id:e.target;
    if(s===selected||t===selected){conn.add(s);conn.add(t);}
  });
  nodeEls.classed('dimmed',d=>!conn.has(d.id)).classed('highlighted',d=>d.id===selected);
  linkEls.classed('dimmed',e=>{ const s=typeof e.source==='object'?e.source.id:e.source, t=typeof e.target==='object'?e.target.id:e.target; return s!==selected&&t!==selected; })
         .classed('highlighted',e=>{ const s=typeof e.source==='object'?e.source.id:e.source, t=typeof e.target==='object'?e.target.id:e.target; return s===selected||t===selected; });
}
function updateVisibility() { /* filter buttons only affect edge display, not subgraph */ applyEdgeFilter(); }
function applyEdgeFilter() {
  if (!linkEls) return;
  linkEls.attr('display', e => isEdgeVisible(e) ? null : 'none');
}

// ══ SIDE PANEL ════════════════════════════════════════════════════════════════
function renderPanel(app) {
  const title=document.getElementById('panel-title'), subtitle=document.getElementById('panel-subtitle'), body=document.getElementById('panel-body');
  if (!app) { title.textContent='SELECT AN APP'; subtitle.textContent='Click any node to inspect'; body.innerHTML=''; return; }

  title.textContent = app.name;
  subtitle.textContent = `${app.model_count} model${app.model_count!==1?'s':''} · in ${app.in_degree} · out ${app.out_degree}`;
  const outEdges=edges.filter(e=>e.source===app.name), inEdges=edges.filter(e=>e.target===app.name);
  let html='';

  if (app.in_import_cycle) {
    const c=cycles.filter(x=>x.kind==='import')[app.import_cycle_index];
    const dp=directImportCycles.filter(d=>d.a===app.name||d.b===app.name);
    html+=`<div class="panel-section" style="border-left:2px solid ${CYCLE_COLOR};padding-left:14px">
      <h3 style="color:${CYCLE_COLOR}">⟳ IMPORT CYCLE</h3>
      <div style="font-family:var(--font-mono);font-size:10px;color:var(--muted);margin-bottom:4px">${c?c.label:''}</div>
      ${c&&c.example_path?`<div style="font-family:var(--font-mono);font-size:9px;color:#fdba74"><b>e.g.</b> ${c.example_path}</div>`:''}
    </div>`;
    if (dp.length) html+=`<div class="panel-section"><h3 style="color:${CYCLE_COLOR}">DIRECT MUTUAL IMPORTS</h3>
      ${dp.map(d=>`<div style="font-family:var(--font-mono);font-size:10px;color:#fdba74;line-height:1.8">↔ ${d.a===app.name?d.b:d.a}</div>`).join('')}
      <div style="font-size:9px;color:var(--muted);margin-top:4px">Start here when refactoring</div></div>`;
  }
  if (app.in_fk_cycle) {
    const c=cycles.filter(x=>x.kind==='fk')[app.fk_cycle_index];
    const dp=directFkCycles.filter(d=>d.a===app.name||d.b===app.name);
    html+=`<div class="panel-section" style="border-left:2px solid ${FK_CYCLE_COLOR};padding-left:14px">
      <h3 style="color:${FK_CYCLE_COLOR}">⟳ FK CYCLE</h3>
      ${dp.length?dp.map(d=>`<div style="font-family:var(--font-mono);font-size:10px;color:#fde68a;line-height:1.8">↔ ${d.a===app.name?d.b:d.a}</div>`).join('')
        :`<div style="font-family:var(--font-mono);font-size:10px;color:#fde68a">${c?c.label:''}</div>`}
      <div style="font-size:9px;color:var(--muted);margin-top:4px">Circular FK — migration ordering risk</div>
    </div>`;
  }
  if (app.models.length) html+=`<div class="panel-section"><h3>Models</h3>${app.models.map(m=>`<span class="model-chip">${m}</span>`).join('')}</div>`;

  const inst = app.in_degree+app.out_degree>0 ? (app.out_degree/(app.in_degree+app.out_degree)).toFixed(2) : null;
  html+=`<div class="panel-section"><h3>Coupling Metrics</h3>
    <div class="metric-row"><span class="label">afferent (fan-in)</span><span class="value">${app.in_degree}</span></div>
    <div class="metric-row"><span class="label">efferent (fan-out)</span><span class="value">${app.out_degree}</span></div>
    ${inst!==null?`<div class="metric-row"><span class="label">instability</span><span class="value">${inst}</span></div>`:''}
  </div>`;
  if (outEdges.length) html+=`<div class="panel-section"><h3>Depends On ↓</h3>${outEdges.map(e=>depRow(e.target,e)).join('')}</div>`;
  if (inEdges.length)  html+=`<div class="panel-section"><h3>Depended On By ↑</h3>${inEdges.map(e=>depRow(e.source,e)).join('')}</div>`;
  body.innerHTML=html;
}

function depRow(appName, edge) {
  const color = edge.in_import_cycle ? CYCLE_COLOR : edge.in_fk_cycle ? FK_CYCLE_COLOR : COLORS[edge.violation?'violation':edge.coupling];
  return `<div class="dep-row"><div class="dot" style="background:${color}"></div><span class="app-name">${appName}</span><span class="coupling-label" style="color:${color};border-color:${color}40">${edge.types.join('+')}</span></div>`;
}

// ══ DAGRE / FORCE LAYOUTS ═════════════════════════════════════════════════════
function applyDagreLayout() {
  const gr=new dagre.graphlib.Graph();
  gr.setGraph({rankdir:'BT',ranksep:80,nodesep:50,marginx:40,marginy:40});
  gr.setDefaultEdgeLabel(()=>({}));
  nodes.forEach(n=>gr.setNode(n.id,{width:nodeR(n)*2+20,height:nodeR(n)*2+20}));
  links.forEach(e=>{
    const s=typeof e.source==='object'?e.source.id:e.source, t=typeof e.target==='object'?e.target.id:e.target;
    if(isEdgeVisible(e)) gr.setEdge(s,t);
  });
  dagre.layout(gr);
  sim.stop();
  nodes.forEach(n=>{ const p=gr.node(n.id); if(p){n.x=n.fx=p.x;n.y=n.fy=p.y;} });
  const gi=gr.graph(), vw=document.getElementById('svg').clientWidth, vh=document.getElementById('svg').clientHeight;
  const sc=Math.min(0.9,Math.min(vw/(gi.width+80),vh/(gi.height+80)));
  d3.select('#svg').call(zoom.transform,d3.zoomIdentity.translate((vw-gi.width*sc)/2,(vh-gi.height*sc)/2).scale(sc));
  linkEls.attr('d',edgePath);
  nodeEls.attr('transform',d=>`translate(${d.x},${d.y})`);
}
function applyForceLayout() {
  nodes.forEach(n=>{n.fx=null;n.fy=null;});
  sim.force('center',d3.forceCenter(w()/2,h()/2)).alpha(0.5).restart();
}

// ══ CORE REBUILD (called any time the visible set or data changes) ═════════════
function rebuildVisualization(graph) {
  if (sim) sim.stop();
  g.selectAll('.links,.nodes').remove();

  apps               = Object.values(graph.apps);
  edges              = graph.edges;
  stats              = graph.stats;
  cycles             = graph.cycles               || [];
  directImportCycles = graph.direct_import_cycles || [];
  directFkCycles     = graph.direct_fk_cycles     || [];
  maxModels          = Math.max(...apps.map(a=>a.model_count), 1);
  nodes              = apps.map(a=>({...a, id:a.name}));
  links              = edges.map(e=>({...e}));
  selected           = null;

  updateStats();
  buildLinks();
  buildNodes();
  buildSimulation();
  applyEdgeFilter();
  buildAppList();
  renderPanel(null);

  if (currentLayout === 'hierarchy') setTimeout(applyDagreLayout, 300);
}

// Recompute subgraph from FULL_GRAPH + current hiddenApps, then rebuild
function rebuildFromHiddenApps() {
  const subgraph = computeSubgraph(hiddenApps);
  rebuildVisualization(subgraph);
}

// loadGraph: called by initial load and Refresh — sets FULL_GRAPH, preserves hiddenApps
function loadGraph(graph) {
  FULL_GRAPH = graph;
  rebuildFromHiddenApps();
}

// ══ REFRESH ═══════════════════════════════════════════════════════════════════
async function refreshGraph() {
  const btn=document.getElementById('refresh-btn'), orig=btn.textContent;
  btn.textContent='↻ running…'; btn.disabled=true;
  try {
    const res=await fetch(REFRESH_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    loadGraph(await res.json());
    btn.textContent='✓ done'; setTimeout(()=>{btn.textContent=orig;btn.disabled=false;},2000);
  } catch(e) {
    btn.textContent='✗ failed'; console.error(e); setTimeout(()=>{btn.textContent=orig;btn.disabled=false;},3000);
  }
}

// ══ APP LIST SIDEBAR ══════════════════════════════════════════════════════════
function appDotColor(appName) {
  if (!FULL_GRAPH) return '#2d3748';
  const fullApp = FULL_GRAPH.apps[appName];
  const out = (FULL_GRAPH.edges || []).filter(e=>e.source===appName);
  if (out.some(e=>e.violation))            return COLORS.violation;
  if (fullApp && fullApp.in_import_cycle)  return CYCLE_COLOR;
  if (fullApp && fullApp.in_fk_cycle)      return FK_CYCLE_COLOR;
  if (out.some(e=>e.coupling==='both'))    return COLORS.both;
  if (out.some(e=>e.coupling==='import'))  return COLORS.import;
  if (out.some(e=>e.coupling==='fk'))      return COLORS.fk;
  return '#2d3748';
}

function buildAppList(filterText) {
  const container=document.getElementById('app-list-items');
  container.innerHTML='';
  const q=(filterText||'').toLowerCase();
  // Use FULL_GRAPH apps so hidden apps are still shown in the list
  const allApps = FULL_GRAPH ? Object.values(FULL_GRAPH.apps) : [];
  allApps.filter(a=>!q||a.name.toLowerCase().includes(q))
    .sort((a,b)=>a.name.localeCompare(b.name))
    .forEach(a=>{
      const color=appDotColor(a.name), isHidden=hiddenApps.has(a.name);
      const item=document.createElement('div');
      item.className='app-item'+(isHidden?' hidden-app':'');
      item.dataset.app=a.name;
      item.title=isHidden?`Show ${a.name}`:`Hide ${a.name}`;
      // Third-party indicator
      const tpBadge = a.is_third_party ? `<span style="font-size:8px;color:var(--muted);margin-left:2px" title="Third-party / Django built-in">3P</span>` : '';
      item.innerHTML=`
        <div class="app-item-dot" style="background:${isHidden?'transparent':color};border-color:${color}"></div>
        <span class="app-item-name">${a.name}</span>
        ${tpBadge}
        ${a.model_count?`<span class="app-item-count">${a.model_count}</span>`:''}
      `;
      item.addEventListener('click',()=>toggleApp(a.name));
      container.appendChild(item);
    });
}

function toggleApp(appName) {
  hiddenApps.has(appName) ? hiddenApps.delete(appName) : hiddenApps.add(appName);
  // Debounce: wait 120ms after last toggle before rebuilding
  clearTimeout(_rebuildTimer);
  _rebuildTimer = setTimeout(()=>{ rebuildFromHiddenApps(); buildAppList(document.getElementById('app-search').value); }, 120);
  // Update the item appearance immediately so clicks feel responsive
  const item = document.querySelector(`[data-app="${appName}"]`);
  if (item) item.classList.toggle('hidden-app', hiddenApps.has(appName));
}

document.getElementById('btn-show-all').addEventListener('click',()=>{
  hiddenApps.clear(); rebuildFromHiddenApps(); buildAppList(document.getElementById('app-search').value);
});
document.getElementById('btn-hide-all').addEventListener('click',()=>{
  if (FULL_GRAPH) Object.keys(FULL_GRAPH.apps).forEach(n=>hiddenApps.add(n));
  rebuildFromHiddenApps(); buildAppList(document.getElementById('app-search').value);
});

// "3rd party" preset button
document.getElementById('btn-hide-3p').addEventListener('click', ()=>{
  const btn = document.getElementById('btn-hide-3p');
  // Toggle: if all 3P are hidden, show them; otherwise hide them
  const thirdParty = FULL_GRAPH ? Object.values(FULL_GRAPH.apps).filter(a=>a.is_third_party).map(a=>a.name) : [];
  const allHidden = thirdParty.length > 0 && thirdParty.every(n=>hiddenApps.has(n));
  thirdParty.forEach(n => allHidden ? hiddenApps.delete(n) : hiddenApps.add(n));
  btn.textContent = allHidden ? '3P' : '3P ✓';
  rebuildFromHiddenApps(); buildAppList(document.getElementById('app-search').value);
});

document.getElementById('app-search').addEventListener('input', e=>buildAppList(e.target.value));

// ══ EXPORT (Mermaid + DOT) ════════════════════════════════════════════════
let exportTab = 'mermaid';

function visibleApps() {
  return apps ? apps.map(a => a.name) : [];
}
function visibleEdges() {
  return edges ? edges.filter(e => isEdgeVisible(e)) : [];
}

function edgeLabel(e) {
  return e.types.join('+');
}

function nodeColor(app) {
  if (app.in_import_cycle) return CYCLE_COLOR;
  if (app.in_fk_cycle)     return FK_CYCLE_COLOR;
  const out = (edges || []).filter(e => e.source === app.name);
  if (out.some(e => e.violation))            return COLORS.violation;
  if (out.some(e => e.coupling === 'both'))  return COLORS.both;
  if (out.some(e => e.coupling === 'import'))return COLORS.import;
  if (out.some(e => e.coupling === 'fk'))    return COLORS.fk;
  return '#2d3748';
}

function generateMermaid() {
  const direction = currentLayout === 'hierarchy' ? 'BT' : 'LR';
  const lines = [`flowchart ${direction}`];

  const vApps   = visibleApps();
  const vEdges  = visibleEdges();
  const appObjs = apps || [];

  // Nodes
  appObjs.forEach(a => {
    const label = a.model_count > 0 ? `${a.name}\n${a.model_count}m` : a.name;
    lines.push(`    ${_mId(a.name)}(["${label}"])`);
  });

  lines.push('');

  // Edges
  vEdges.forEach(e => {
    const s = typeof e.source === 'object' ? e.source.id : e.source;
    const t = typeof e.target === 'object' ? e.target.id : e.target;
    const arrow = e.coupling === 'fk' ? '-->' : e.coupling === 'import' ? '-.->' : '==>';
    lines.push(`    ${_mId(s)} ${arrow}|"${edgeLabel(e)}"| ${_mId(t)}`);
  });

  lines.push('');

  // ClassDefs for cycle / violation styling
  const importCycleApps = appObjs.filter(a => a.in_import_cycle).map(a => _mId(a.name));
  const fkCycleApps     = appObjs.filter(a => a.in_fk_cycle && !a.in_import_cycle).map(a => _mId(a.name));
  const violationApps   = [...new Set(vEdges.filter(e => e.violation).map(e => {
    const s = typeof e.source === 'object' ? e.source.id : e.source;
    return _mId(s);
  }))];

  lines.push('    classDef importCycle fill:#1c0e00,stroke:#f97316,color:#fdba74');
  lines.push('    classDef fkCycle     fill:#1c1500,stroke:#eab308,color:#fde68a');
  lines.push('    classDef violation   fill:#1c0000,stroke:#ef4444,color:#fca5a5');

  if (importCycleApps.length) lines.push(`    class ${importCycleApps.join(',')} importCycle`);
  if (fkCycleApps.length)     lines.push(`    class ${fkCycleApps.join(',')} fkCycle`);
  if (violationApps.length)   lines.push(`    class ${violationApps.join(',')} violation`);

  return lines.join('\n');
}

function _mId(name) {
  // Mermaid node IDs can't contain dots or hyphens — replace with underscores
  return name.replace(/[^a-zA-Z0-9_]/g, '_');
}

function generateDot() {
  const direction = currentLayout === 'hierarchy' ? 'BT' : 'TB';
  const appObjs = apps || [];
  const vEdges  = visibleEdges();
  const lines = [
    `digraph dependency_map {`,
    `  rankdir=${direction};`,
    `  splines=curved;`,
    `  node [fontname="monospace" shape=box style="rounded,filled" fillcolor="#0d1117" fontcolor="#c9d1d9" color="#2d3748"];`,
    `  edge [fontname="monospace" fontsize=9 fontcolor="#586069"];`,
    '',
  ];

  appObjs.forEach(a => {
    const label = a.model_count > 0 ? `${a.name}\\n${a.model_count} model${a.model_count !== 1 ? 's' : ''}` : a.name;
    const color = nodeColor(a);
    lines.push(`  "${a.name}" [label="${label}" color="${color}"];`);
  });

  lines.push('');

  vEdges.forEach(e => {
    const s = typeof e.source === 'object' ? e.source.id : e.source;
    const t = typeof e.target === 'object' ? e.target.id : e.target;
    let color = COLORS[e.violation ? 'violation' : e.coupling];
    if (e.in_import_cycle) color = CYCLE_COLOR;
    if (e.in_fk_cycle)     color = FK_CYCLE_COLOR;
    const style = e.coupling === 'import' && !e.in_import_cycle ? 'dashed' : 'solid';
    lines.push(`  "${s}" -> "${t}" [label="${edgeLabel(e)}" color="${color}" style=${style}];`);
  });

  lines.push('}');
  return lines.join('\n');
}

function renderExportContent() {
  const content = exportTab === 'mermaid' ? generateMermaid() : generateDot();
  document.getElementById('export-content').textContent = content;
  const vApps  = visibleApps().length;
  const vEdges = visibleEdges().length;
  document.getElementById('export-subtitle').textContent =
    `${vApps} apps · ${vEdges} edges · ${exportTab === 'mermaid' ? 'paste into any Markdown file or Mermaid Live' : 'render with: dot -Tsvg deps.dot > deps.svg'}`;
}

document.getElementById('export-btn').addEventListener('click', () => {
  renderExportContent();
  document.getElementById('export-modal').style.display = 'flex';
});
document.getElementById('export-close').addEventListener('click', () => {
  document.getElementById('export-modal').style.display = 'none';
});
document.getElementById('export-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('export-modal'))
    document.getElementById('export-modal').style.display = 'none';
});
document.getElementById('export-copy').addEventListener('click', () => {
  const text = document.getElementById('export-content').textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('export-copy');
    btn.textContent = 'copied!';
    setTimeout(() => btn.textContent = 'copy', 2000);
  });
});

['mermaid', 'dot'].forEach(tab => {
  document.getElementById(`export-tab-${tab}`).addEventListener('click', () => {
    exportTab = tab;
    document.getElementById('export-tab-mermaid').classList.toggle('active', tab === 'mermaid');
    document.getElementById('export-tab-dot').classList.toggle('active', tab === 'dot');
    renderExportContent();
  });
});

// ══ RESIZE ════════════════════════════════════════════════════════════════════
new ResizeObserver(()=>{
  if (currentLayout==='force'&&sim) { sim.force('center',d3.forceCenter(w()/2,h()/2)); sim.alpha(0.1).restart(); }
}).observe(document.getElementById('canvas'));

// ══ INITIAL LOAD ══════════════════════════════════════════════════════════════
loadGraph(__GRAPH_JSON__);

// ══ HIGHLIGHT from ?highlight= query param ════════════════════════════════
if (HIGHLIGHT_APPS.length) {
  // Mark highlighted apps in the sidebar with a request-origin dot colour.
  // After the simulation settles, also auto-scroll the first one into view.
  setTimeout(function () {
    HIGHLIGHT_APPS.forEach(function (appName) {
      var item = document.querySelector('[data-app="' + appName + '"]');
      if (item) {
        var dot = item.querySelector('.app-item-dot');
        if (dot) {
          dot.style.boxShadow = '0 0 0 2px #0070c0';
          dot.title = 'touched in request';
        }
        item.style.fontWeight = '600';
      }
    });
    // Scroll first highlighted app into view in the sidebar.
    var first = document.querySelector('[data-app="' + HIGHLIGHT_APPS[0] + '"]');
    if (first) first.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, 600);  // wait for simulation to settle
}

// ══ AUTO-REFRESH (polls version endpoint, refreshes on server restart) ════
if (VERSION_URL && REFRESH_URL) {
  let _knownEpoch = null;
  let _autoRefreshTimer = null;

  async function pollVersion() {
    try {
      const res = await fetch(VERSION_URL);
      if (!res.ok) return;
      const data = await res.json();
      const epoch = data.epoch;
      if (_knownEpoch === null) {
        _knownEpoch = epoch;
      } else if (epoch !== _knownEpoch) {
        _knownEpoch = epoch;
        refreshGraph();
      }
    } catch (e) {
      // Server down (restarting) — ignore, next poll will catch it
    }
  }

  _autoRefreshTimer = setInterval(pollVersion, 3000);
}
</script>
</body>

</html>"""