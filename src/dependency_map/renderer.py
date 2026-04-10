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
    root_packages: list[str] | None = None,
) -> str:
    """Return a self-contained HTML string visualising *graph*."""
    import json as _json
    graph_json  = json.dumps(graph, indent=2)
    colors_json = json.dumps(COUPLING_COLORS)
    highlight_json = _json.dumps(highlight_apps or [])
    root_packages_json = _json.dumps(root_packages or [])

    return (
        _HTML_TEMPLATE
        .replace("__TITLE__", title)
        .replace("__GRAPH_JSON__", graph_json)
        .replace("__COLORS_JSON__", colors_json)
        .replace("__REFRESH_URL__", refresh_url)
        .replace("__VERSION_URL__", version_url)
        .replace("__HIGHLIGHT_APPS__", highlight_json)
        .replace("__ROOT_PACKAGES__", root_packages_json)
    )


def write_html(
    graph: dict,
    output_path: str | Path,
    title: str = "Django Dependency Map",
    refresh_url: str = "",
    highlight_apps: list[str] | None = None,
    root_packages: list[str] | None = None,
):
    html = render_html(graph, title, refresh_url=refresh_url, highlight_apps=highlight_apps, root_packages=root_packages)
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

/* ── Display options dropdown ──────────────────────────────── */
.display-btn {
  font-family: var(--font-mono);
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  background: transparent;
  color: var(--muted);
  transition: color .15s, border-color .15s;
  position: relative;
}
.display-btn:hover { color: var(--text); border-color: var(--accent); }
.display-btn.open  { color: var(--text); border-color: var(--accent); }

.display-menu {
  display: none;
  position: absolute;
  top: 38px;
  right: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 0;
  min-width: 180px;
  box-shadow: 0 4px 16px rgba(0,0,0,.4);
  z-index: 100;
}
.display-menu.visible { display: block; }

.display-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  cursor: pointer;
  transition: background .1s, color .1s;
  user-select: none;
}
.display-option:hover { background: rgba(255,255,255,.05); color: var(--text); }
.display-option.active { color: var(--text); }
.display-option .check {
  width: 14px;
  height: 14px;
  border: 1px solid var(--border);
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  flex-shrink: 0;
}
.display-option.active .check { background: var(--accent); border-color: var(--accent); color: #fff; }

/* ── Import count labels on edges ──────────────────────────── */
.import-count-label {
  font-family: var(--font-mono);
  font-size: 9px;
  fill: var(--muted);
  pointer-events: none;
  text-anchor: middle;
  dominant-baseline: central;
}

/* ── Cycle break suggestion ────────────────────────────────── */
.link.break-suggestion {
  stroke-dasharray: 4,4 !important;
  filter: drop-shadow(0 0 3px rgba(251,191,36,.4));
}

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
    <div style="position:relative;margin-left:4px">
      <button class="display-btn" id="display-btn" title="Display options">⚙</button>
      <div class="display-menu" id="display-menu">
        <div class="display-option" data-option="importCounts">
          <span class="check"></span> Import counts
        </div>
        <div class="display-option" data-option="cycleBreaker">
          <span class="check"></span> Cycle breaker
        </div>
      </div>
    </div>
    <button id="refresh-btn" class="refresh-btn" style="display:none" title="Re-run analysis">↻ refresh</button>
    <button id="export-btn" class="refresh-btn" title="Export visible graph (Mermaid / DOT / import-linter Rules)">⬡ export</button>
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

<!-- Export panel (bottom-docked) -->
<div id="export-modal" style="display:none;position:fixed;bottom:0;left:180px;right:300px;z-index:200;background:var(--surface);border-top:2px solid var(--border);max-height:45vh;flex-direction:column;overflow:hidden;box-shadow:0 -4px 24px rgba(0,0,0,.5);">
  <div style="padding:10px 18px 8px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;">
    <span style="font-family:var(--font-mono);font-size:13px;color:var(--accent);font-weight:500">Export visible graph</span>
    <div style="margin-left:auto;display:flex;gap:6px;">
      <button id="export-tab-mermaid" class="layout-btn active" style="font-size:10px;padding:2px 8px">Mermaid</button>
      <button id="export-tab-dot"     class="layout-btn"        style="font-size:10px;padding:2px 8px">DOT</button>
      <button id="export-tab-rules"   class="layout-btn"        style="font-size:10px;padding:2px 8px">Rules</button>
    </div>
    <button id="export-copy" class="refresh-btn" style="margin-left:8px">copy</button>
    <button id="export-close" style="background:none;border:none;color:var(--muted);font-size:18px;cursor:pointer;line-height:1;padding:0 4px">&times;</button>
  </div>
  <div style="padding:4px 12px 3px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
    <span style="font-family:var(--font-mono);font-size:10px;color:var(--muted)" id="export-subtitle"></span>
  </div>
  <!-- Rules options bar — visible only when Rules tab is active -->
  <div id="rules-options" style="display:none;padding:6px 14px;border-bottom:1px solid var(--border);flex-direction:column;gap:6px;">
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="font-family:var(--font-mono);font-size:10px;color:var(--muted)">Contract type:</span>
      <button id="rules-mode-forbidden" class="layout-btn active" style="font-size:10px;padding:2px 8px">Forbidden</button>
      <button id="rules-mode-layers"    class="layout-btn"        style="font-size:10px;padding:2px 8px">Layers</button>
      <span style="font-family:var(--font-mono);font-size:10px;color:var(--muted);margin-left:auto;">Layer grouping:</span>
      <button id="rules-layers-strict"  class="layout-btn active" style="font-size:10px;padding:2px 8px" disabled>Strict</button>
      <button id="rules-layers-grouped" class="layout-btn"        style="font-size:10px;padding:2px 8px" disabled>Grouped</button>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <label style="font-family:var(--font-mono);font-size:10px;color:var(--muted);">Root package:</label>
      <input id="rules-root-pkg" type="text" style="font-family:var(--font-mono);font-size:11px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:2px 8px;width:200px;" autocomplete="off">
      <span style="font-family:var(--font-mono);font-size:9px;color:var(--muted)">module prefix for generated paths (check this is correct)</span>
    </div>
  </div>
  <!-- Cycle-breaking panel — shown when layers mode has cycles -->
  <div id="rules-cycles" style="display:none;padding:8px 14px;border-bottom:1px solid var(--border);max-height:140px;overflow-y:auto;background:rgba(249,115,22,.05);">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
      <span style="font-family:var(--font-mono);font-size:11px;color:#f97316;font-weight:500">Cycles detected — select edges to ignore:</span>
      <button id="rules-accept-suggested" class="refresh-btn" style="font-size:10px;padding:2px 8px;margin-left:auto">accept suggestions</button>
    </div>
    <div id="rules-cycle-edges" style="font-family:var(--font-mono);font-size:10px;"></div>
  </div>
  <pre id="export-content" style="flex:1;overflow:auto;margin:0;padding:12px 16px;font-family:var(--font-mono);font-size:11px;color:var(--text);background:var(--bg);white-space:pre;"></pre>
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
const ROOT_PACKAGES  = __ROOT_PACKAGES__;    // ['myproject'] — used by rules export

// ══ MUTABLE GRAPH STATE ══════════════════════════════════════════════════════
let FULL_GRAPH;                          // source of truth — never filtered
let apps, edges, stats, cycles, directImportCycles, directFkCycles;
let nodes, links, nodeEls, linkEls, countLabelEls, sim;
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

// ══ DISPLAY OPTIONS ══════════════════════════════════════════════════════════
const displayOptions = new Set();
const displayBtn  = document.getElementById('display-btn');
const displayMenu = document.getElementById('display-menu');

displayBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  displayMenu.classList.toggle('visible');
  displayBtn.classList.toggle('open');
});
document.addEventListener('click', () => {
  displayMenu.classList.remove('visible');
  displayBtn.classList.remove('open');
});
displayMenu.addEventListener('click', (e) => e.stopPropagation());

document.querySelectorAll('.display-option').forEach(opt => {
  opt.addEventListener('click', () => {
    const key = opt.dataset.option;
    if (displayOptions.has(key)) {
      displayOptions.delete(key);
      opt.classList.remove('active');
      opt.querySelector('.check').textContent = '';
    } else {
      displayOptions.add(key);
      opt.classList.add('active');
      opt.querySelector('.check').textContent = '✓';
    }
    updateDisplayOptions();
  });
});

function updateDisplayOptions() {
  // Import count labels
  if (countLabelEls) {
    countLabelEls.attr('display', displayOptions.has('importCounts') ? null : 'none');
  }
  // Cycle breaker styling
  if (linkEls) {
    linkEls.classed('break-suggestion', d => displayOptions.has('cycleBreaker') && d.is_break_suggestion);
  }
}

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
      if (d.import_count>0)  html+=`<div class="tt-row">imports: <strong>${d.import_count}</strong></div>`;
      if (d.in_import_cycle) html+=`<div class="tt-row" style="color:${CYCLE_COLOR}">⟳ import cycle</div>`;
      if (d.in_fk_cycle)     html+=`<div class="tt-row" style="color:${FK_CYCLE_COLOR}">⟳ FK cycle</div>`;
      if (d.violation)       html+=`<div class="tt-row" style="color:var(--violation)">⚠ violation</div>`;
      if (d.is_break_suggestion) html+=`<div class="tt-row" style="color:#fbbf24">✂ suggested cycle break</div>`;
      if (d.model_edges.length) {
        const typeLabels = {fk:'FK',o2o:'O2O',m2m:'M2M',generic:'Generic'};
        html+=`<div class="tt-row" style="margin-top:6px;color:var(--muted)">Model relations:</div>`;
        d.model_edges.slice(0,5).forEach(me=>{
          const tag = typeLabels[me.type]||'FK';
          const detail = me.label ? `${tag}: ${me.label}` : tag;
          html+=`<div class="tt-row">&nbsp;&nbsp;${me.from} → ${me.to} <span style="color:var(--muted)">(${detail})</span></div>`;
        });
        if (d.model_edges.length>5) html+=`<div class="tt-row" style="color:var(--muted)">+${d.model_edges.length-5} more</div>`;
      }
      tooltip.innerHTML=html; tooltip.classList.add('visible');
      tooltip.style.left=(event.clientX+14)+'px'; tooltip.style.top=(event.clientY-10)+'px';
    })
    .on('mousemove.move', ev=>{ tooltip.style.left=(ev.clientX+14)+'px'; tooltip.style.top=(ev.clientY-10)+'px'; })
    .on('mouseleave', ()=>tooltip.classList.remove('visible'));

  // Import count labels (hidden by default, toggled via display options)
  countLabelEls = g.select('.links').selectAll('text.import-count-label').data(links.filter(d=>d.import_count>0)).join('text')
    .attr('class','import-count-label')
    .text(d=>d.import_count)
    .attr('display', displayOptions.has('importCounts') ? null : 'none');
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
  sim.on('tick',()=>{
    linkEls.attr('d',edgePath);
    nodeEls.attr('transform',d=>`translate(${d.x},${d.y})`);
    if (countLabelEls) countLabelEls
      .attr('x', d=>{ const s=typeof d.source==='object'?d.source:{}; const t=typeof d.target==='object'?d.target:{}; return ((s.x||0)+(t.x||0))/2; })
      .attr('y', d=>{ const s=typeof d.source==='object'?d.source:{}; const t=typeof d.target==='object'?d.target:{}; return ((s.y||0)+(t.y||0))/2 - 6; });
  });
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
  if (countLabelEls) {
    countLabelEls.attr('display', d => isEdgeVisible(d) && displayOptions.has('importCounts') ? null : 'none');
  }
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
  if (countLabelEls) countLabelEls
    .attr('x', d=>{ const s=typeof d.source==='object'?d.source:{}; const t=typeof d.target==='object'?d.target:{}; return ((s.x||0)+(t.x||0))/2; })
    .attr('y', d=>{ const s=typeof d.source==='object'?d.source:{}; const t=typeof d.target==='object'?d.target:{}; return ((s.y||0)+(t.y||0))/2 - 6; });
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
  updateDisplayOptions();
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

// ── Rules export state ───────────────────────────────────────────────────
let rulesMode     = 'forbidden'; // 'forbidden' | 'layers'
let layersGrouping = 'strict';   // 'strict' | 'grouped'
const rulesIgnoredEdges = new Set(); // "source|target" keys the user chose to ignore

function _appToModule(appName) {
  const root = document.getElementById('rules-root-pkg').value.trim();
  return root ? `${root}.${appName}` : appName;
}

// ── Forbidden rules ──────────────────────────────────────────────────────
function generateForbiddenRules() {
  const root = document.getElementById('rules-root-pkg').value.trim();
  const vEdges = visibleEdges().filter(e => e.types && e.types.includes('import'));
  const lines = [
    '[importlinter]',
    'root_packages =',
    `    ${root || 'myproject'}`,
    '',
  ];

  vEdges.forEach((e, i) => {
    const s = typeof e.source === 'object' ? e.source.id : e.source;
    const t = typeof e.target === 'object' ? e.target.id : e.target;
    // Edge s→t exists. Generate: "t must not import s" (reverse guard).
    // If s→t was marked as cycle breaker, skip — the reverse edge's
    // contract will carry the ignore_imports for this direction instead.
    if (rulesIgnoredEdges.has(`${s}|${t}`)) return;
    const contractName = `${t}-cannot-import-${s}`.replace(/[^a-zA-Z0-9_-]/g, '-');
    lines.push(`[importlinter:contract:${contractName}]`);
    lines.push(`name = ${t} must not import ${s}`);
    lines.push('type = forbidden');
    lines.push(`source_modules = ${_appToModule(t)}`);
    lines.push(`forbidden_modules = ${_appToModule(s)}`);
    // If the reverse edge (t→s) was marked as cycle breaker, add
    // ignore_imports so the contract acknowledges the existing violation.
    if (rulesIgnoredEdges.has(`${t}|${s}`)) {
      lines.push('ignore_imports =');
      lines.push(`    ${_appToModule(s)} -> ${_appToModule(t)}`);
    }
    lines.push('');
  });

  return lines.join('\n');
}

// ── Layers rules ─────────────────────────────────────────────────────────

// Kahn's algorithm topological sort, returns layers (array of arrays).
// Returns null if graph has cycles (after removing ignoredEdges).
function topoSortLayers(appNames, importEdges, ignoredEdges) {
  const adj = {};
  const inDeg = {};
  appNames.forEach(a => { adj[a] = []; inDeg[a] = 0; });

  importEdges.forEach(e => {
    const s = typeof e.source === 'object' ? e.source.id : e.source;
    const t = typeof e.target === 'object' ? e.target.id : e.target;
    const key = `${s}|${t}`;
    if (ignoredEdges.has(key)) return;
    if (!adj[s] || !adj[t]) return; // skip edges to/from hidden apps
    adj[s].push(t);
    inDeg[t] = (inDeg[t] || 0) + 1;
  });

  // Kahn's: peel off zero-indegree nodes layer by layer
  const layers = [];
  let remaining = new Set(appNames);

  while (remaining.size > 0) {
    const layer = [...remaining].filter(n => (inDeg[n] || 0) === 0);
    if (layer.length === 0) return null; // cycle remains
    layers.push(layer.sort());
    layer.forEach(n => {
      remaining.delete(n);
      (adj[n] || []).forEach(m => { inDeg[m]--; });
    });
  }

  // layers[0] = top (most dependent), layers[last] = bottom (depended-on leaf)
  return layers;
}

// Find edges that participate in cycles (for the cycle-breaking UI).
// Uses the FULL edge set (ignoring nothing) so that already-checked
// edges stay visible as checkboxes rather than vanishing.
function findCycleEdges(appNames, importEdges) {
  const visible = importEdges.filter(e => {
    const s = typeof e.source === 'object' ? e.source.id : e.source;
    const t = typeof e.target === 'object' ? e.target.id : e.target;
    return appNames.includes(s) && appNames.includes(t);
  });
  const sccs = tarjanSCCs(visible, 'import');
  const sccMembers = new Set();
  sccs.forEach(scc => scc.forEach(n => sccMembers.add(n)));

  return visible.filter(e => {
    const s = typeof e.source === 'object' ? e.source.id : e.source;
    const t = typeof e.target === 'object' ? e.target.id : e.target;
    return sccMembers.has(s) && sccMembers.has(t) && e.types && e.types.includes('import');
  }).map(e => {
    const s = typeof e.source === 'object' ? e.source.id : e.source;
    const t = typeof e.target === 'object' ? e.target.id : e.target;
    return { source: s, target: t, is_break_suggestion: !!e.is_break_suggestion };
  });
}

function renderCycleBreakingUI() {
  const appNames = visibleApps();
  const vEdges = edges || [];
  const cycleEdges = findCycleEdges(appNames, vEdges);
  const panel = document.getElementById('rules-cycles');
  const container = document.getElementById('rules-cycle-edges');

  if (cycleEdges.length === 0) {
    panel.style.display = 'none';
    return;
  }

  panel.style.display = 'block';
  // Clear previous content safely
  while (container.firstChild) container.removeChild(container.firstChild);

  cycleEdges.forEach(ce => {
    const key = `${ce.source}|${ce.target}`;
    const row = document.createElement('label');
    row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:2px 0;cursor:pointer;color:var(--text);';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = rulesIgnoredEdges.has(key);
    cb.dataset.edgeKey = key;
    cb.addEventListener('change', () => {
      cb.checked ? rulesIgnoredEdges.add(key) : rulesIgnoredEdges.delete(key);
      renderRulesContent();
    });
    const label = document.createElement('span');
    label.textContent = `${ce.source} \u2192 ${ce.target}`;
    if (ce.is_break_suggestion) {
      label.textContent += ' (suggested)';
      label.style.color = '#f97316';
    }
    row.appendChild(cb);
    row.appendChild(label);
    container.appendChild(row);
  });
}

function generateLayersRules() {
  const root = document.getElementById('rules-root-pkg').value.trim();
  const appNames = visibleApps();
  const vEdges = edges || [];
  const importEdges = vEdges.filter(e => e.types && e.types.includes('import'));

  const layers = topoSortLayers(appNames, importEdges, rulesIgnoredEdges);
  if (!layers) {
    return '# ERROR: Cycles remain in the visible graph.\n# Use the checkboxes above to ignore cycle-causing edges.';
  }

  const lines = [
    '[importlinter]',
    'root_packages =',
    `    ${root || 'myproject'}`,
    '',
    '[importlinter:contract:architecture-layers]',
    'name = Architecture layers',
    'type = layers',
    'layers =',
  ];

  if (layersGrouping === 'grouped') {
    // Peers at same topo depth share a line with |
    layers.forEach(layer => {
      lines.push('    ' + layer.map(a => _appToModule(a)).join(' | '));
    });
  } else {
    // Strict: each app on its own line, layers separated by ordering
    layers.forEach(layer => {
      layer.forEach(a => {
        lines.push('    ' + _appToModule(a));
      });
    });
  }

  // Add ignore_imports if any edges were marked
  if (rulesIgnoredEdges.size > 0) {
    lines.push('ignore_imports =');
    [...rulesIgnoredEdges].sort().forEach(key => {
      const [s, t] = key.split('|');
      lines.push(`    ${_appToModule(s)} -> ${_appToModule(t)}`);
    });
  }

  lines.push('');
  return lines.join('\n');
}

// ── Render dispatcher ────────────────────────────────────────────────────

function renderRulesContent() {
  const appNames = visibleApps();
  const vEdges = visibleEdges().filter(e => e.types && e.types.includes('import'));

  renderCycleBreakingUI();

  if (rulesMode === 'layers') {
    const content = generateLayersRules();
    document.getElementById('export-content').textContent = content;
    document.getElementById('export-subtitle').textContent =
      `${appNames.length} apps \u00b7 ${vEdges.length} import edges \u00b7 paste into .importlinter or setup.cfg`;
  } else {
    const content = generateForbiddenRules();
    document.getElementById('export-content').textContent = content;
    document.getElementById('export-subtitle').textContent =
      `${appNames.length} apps \u00b7 ${vEdges.length} import edges \u2192 ${vEdges.length} forbidden contracts \u00b7 paste into .importlinter or setup.cfg`;
  }
}

function renderExportContent() {
  const isRules = exportTab === 'rules';
  document.getElementById('rules-options').style.display = isRules ? 'flex' : 'none';
  if (!isRules) document.getElementById('rules-cycles').style.display = 'none';

  // Enable/disable layer grouping buttons based on rules mode
  const isLayers = rulesMode === 'layers';
  document.getElementById('rules-layers-strict').disabled  = !isLayers;
  document.getElementById('rules-layers-grouped').disabled = !isLayers;

  if (isRules) {
    renderRulesContent();
    return;
  }

  const content = exportTab === 'mermaid' ? generateMermaid() : generateDot();
  document.getElementById('export-content').textContent = content;
  const vApps  = visibleApps().length;
  const vEdges = visibleEdges().length;
  document.getElementById('export-subtitle').textContent =
    `${vApps} apps \u00b7 ${vEdges} edges \u00b7 ${exportTab === 'mermaid' ? 'paste into any Markdown file or Mermaid Live' : 'render with: dot -Tsvg deps.dot > deps.svg'}`;
}

// ── Export modal event handlers ──────────────────────────────────────────

document.getElementById('export-btn').addEventListener('click', () => {
  const panel = document.getElementById('export-modal');
  if (panel.style.display === 'flex') {
    panel.style.display = 'none';
    return;
  }
  // Pre-fill root package from server-injected value
  const input = document.getElementById('rules-root-pkg');
  if (!input.value && ROOT_PACKAGES.length) input.value = ROOT_PACKAGES[0];
  rulesIgnoredEdges.clear();
  renderExportContent();
  panel.style.display = 'flex';
});
document.getElementById('export-close').addEventListener('click', () => {
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

// Tab switching: Mermaid / DOT / Rules
['mermaid', 'dot', 'rules'].forEach(tab => {
  document.getElementById(`export-tab-${tab}`).addEventListener('click', () => {
    exportTab = tab;
    document.getElementById('export-tab-mermaid').classList.toggle('active', tab === 'mermaid');
    document.getElementById('export-tab-dot').classList.toggle('active', tab === 'dot');
    document.getElementById('export-tab-rules').classList.toggle('active', tab === 'rules');
    renderExportContent();
  });
});

// Rules sub-mode switching: Forbidden / Layers
['forbidden', 'layers'].forEach(mode => {
  document.getElementById(`rules-mode-${mode}`).addEventListener('click', () => {
    rulesMode = mode;
    document.getElementById('rules-mode-forbidden').classList.toggle('active', mode === 'forbidden');
    document.getElementById('rules-mode-layers').classList.toggle('active', mode === 'layers');
    document.getElementById('rules-layers-strict').disabled  = mode !== 'layers';
    document.getElementById('rules-layers-grouped').disabled = mode !== 'layers';
    renderExportContent();
  });
});

// Layer grouping switching: Strict / Grouped
['strict', 'grouped'].forEach(g => {
  document.getElementById(`rules-layers-${g}`).addEventListener('click', () => {
    if (rulesMode !== 'layers') return;
    layersGrouping = g;
    document.getElementById('rules-layers-strict').classList.toggle('active', g === 'strict');
    document.getElementById('rules-layers-grouped').classList.toggle('active', g === 'grouped');
    renderExportContent();
  });
});

// Accept all suggested cycle breakers
document.getElementById('rules-accept-suggested').addEventListener('click', () => {
  const checkboxes = document.querySelectorAll('#rules-cycle-edges input[type=checkbox]');
  const hasSuggestions = [...checkboxes].some(cb => {
    return cb.parentElement.textContent.includes('(suggested)');
  });
  checkboxes.forEach(cb => {
    const isSuggested = cb.parentElement.textContent.includes('(suggested)');
    if (isSuggested || !hasSuggestions) {
      cb.checked = true;
      rulesIgnoredEdges.add(cb.dataset.edgeKey);
    }
  });
  renderRulesContent();
});

// Re-render rules when root package changes
document.getElementById('rules-root-pkg').addEventListener('input', () => {
  if (exportTab === 'rules') renderRulesContent();
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