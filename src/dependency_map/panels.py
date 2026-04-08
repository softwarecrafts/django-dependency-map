"""
dependency_map.panels
~~~~~~~~~~~~~~~~~~~~~
Django Debug Toolbar integration — ``DependenciesPanel``.

What it shows
-------------
**This Request tab** — the app that handled the current request (resolved
via Django's URL resolver) plus its direct import dependencies from the
cached dependency graph.

**All Apps tab** — every installed app, with the request app highlighted.

**View full graph** — links to ``/__debug__/depmap/`` with
``?highlight=<app>,<app>`` so the D3 visualisation pre-highlights the
request-related apps.

Setup
-----
Add to ``DEBUG_TOOLBAR_PANELS`` in settings::

    DEBUG_TOOLBAR_PANELS = [
        ...
        "dependency_map.panels.DependenciesPanel",
    ]

No URLconf changes required.

Settings
--------
DEPENDENCY_MAP_PANEL_CACHE_TTL
    Seconds to cache the full dependency graph between requests.
    Default: 60.  Set to 0 to rebuild on every request.
"""
from __future__ import annotations

import threading
import time
from typing import Any

try:
    from debug_toolbar.panels import Panel as _BasePanel
except ImportError as _exc:
    raise ImportError(
        "django-debug-toolbar is required to use DependenciesPanel.\n"
        "Install it with:  pip install django-debug-toolbar"
    ) from _exc


# ---------------------------------------------------------------------------
# Process-level graph cache
# ---------------------------------------------------------------------------

_cache_lock:  threading.Lock = threading.Lock()
_cache_graph: dict | None    = None
_cache_ts:    float          = 0.0


def _get_cache_ttl() -> int:
    from django.conf import settings
    return int(getattr(settings, "DEPENDENCY_MAP_PANEL_CACHE_TTL", 60))


def _get_or_build_graph() -> dict:
    global _cache_graph, _cache_ts
    with _cache_lock:
        ttl = _get_cache_ttl()
        if _cache_graph is None or ttl == 0 or (time.time() - _cache_ts) > ttl:
            from dependency_map.views import (
                _get_root_packages,
                _get_valid_app_labels,
                _run_analysis,
            )
            rp  = _get_root_packages()
            val = _get_valid_app_labels(rp)
            _cache_graph = _run_analysis(rp, val)
            _cache_ts    = time.time()
        return _cache_graph


def invalidate_graph_cache() -> None:
    global _cache_graph
    with _cache_lock:
        _cache_graph = None


# ---------------------------------------------------------------------------
# URL resolution → app label
# ---------------------------------------------------------------------------

def _build_prefix_map() -> dict[str, str]:
    """
    Return {app_config.name: normalised_label} sorted longest-first for
    greedy prefix matching.  Delegates to the shared canonical mapping.
    """
    from dependency_map.analyzer import build_module_to_app_map
    from dependency_map.views import _get_root_packages

    return build_module_to_app_map(_get_root_packages())


def resolve_request_app(request) -> str | None:
    """
    Resolve a request's URL to the Django app label that owns the view.

    Uses ``django.urls.resolve`` to find the view callable, then maps its
    module to an app label via longest-prefix matching.  Returns ``None``
    when the URL can't be resolved or the view doesn't belong to a known app.
    """
    from django.urls import resolve, Resolver404

    try:
        match = resolve(request.path)
    except Resolver404:
        return None

    view_func = match.func
    # CBVs wrapped by as_view() store the class in view_class
    module = getattr(view_func, "__module__", None)
    if not module:
        return None

    return _module_to_app(module)


def _module_to_app(module_name: str) -> str | None:
    """Map a single module name to its app label, or None."""
    prefix_map = _build_prefix_map()
    for pkg_name, label in prefix_map.items():
        if module_name == pkg_name or module_name.startswith(pkg_name + "."):
            return label
    return None


def _collect_request_apps(request_app: str, graph: dict) -> list[str]:
    """
    Given the app that handled the request, return it plus its direct
    import dependencies (outgoing edges) from the graph.
    """
    if not request_app or request_app not in graph.get("apps", {}):
        return [request_app] if request_app else []

    apps = {request_app}
    for edge in graph.get("edges", []):
        if edge["source"] == request_app and "import" in edge.get("types", []):
            apps.add(edge["target"])
    return sorted(apps)


# ---------------------------------------------------------------------------
# Table row construction
# ---------------------------------------------------------------------------

def _build_app_rows(
    graph: dict,
    scope_apps: list[str] | None,
    request_apps: set[str],
) -> list[dict[str, Any]]:
    """
    Build table row dicts.  scope_apps=None means all apps in the graph.
    Each row dict is safe to pass directly as template context.
    """
    edges  = graph.get("edges", [])
    apps   = graph.get("apps", {})
    cycles = graph.get("cycles", [])

    # Index edges
    out_import: dict[str, list[str]] = {}
    out_fk:     dict[str, list[str]] = {}
    in_import:  dict[str, list[str]] = {}
    violations: set[str] = set()

    for edge in edges:
        src, tgt   = edge["source"], edge["target"]
        types      = edge.get("types", [])
        coupling   = edge.get("coupling", "")
        if edge.get("violation"):
            violations.add(src)
        if "import" in types or coupling == "both":
            out_import.setdefault(src, []).append(tgt)
            in_import.setdefault(tgt, []).append(src)
        if coupling == "fk" or "fk" in types:
            out_fk.setdefault(src, []).append(tgt)

    # Index cycle membership
    app_cycles: dict[str, list[dict]] = {}
    for cycle in cycles:
        for name in cycle.get("apps", []):
            app_cycles.setdefault(name, []).append(cycle)

    target = scope_apps if scope_apps is not None else sorted(apps.keys())
    rows: list[dict[str, Any]] = []

    for name in sorted(target):
        app_data  = apps.get(name, {})
        my_cycles = app_cycles.get(name, [])
        imp_cy    = [c for c in my_cycles if c.get("kind") == "import"]
        fk_cy     = [c for c in my_cycles if c.get("kind") == "fk"]

        if imp_cy and fk_cy:
            cycle_kind, cycle_label = "both",   imp_cy[0].get("label", "")
        elif imp_cy:
            cycle_kind, cycle_label = "import", imp_cy[0].get("label", "")
        elif fk_cy:
            cycle_kind, cycle_label = "fk",     fk_cy[0].get("label", "")
        else:
            cycle_kind, cycle_label = "", ""

        rows.append({
            "name":          name,
            "imports_from":  sorted(set(out_import.get(name, []))),
            "imported_by":   sorted(set(in_import.get(name, []))),
            "fk_targets":    sorted(set(out_fk.get(name, []))),
            "in_cycle":      bool(my_cycles),
            "cycle_kind":    cycle_kind,
            "cycle_label":   cycle_label,
            "in_violation":  name in violations,
            "is_third_party": app_data.get("is_third_party", False),
            "is_request":    name in request_apps,
        })

    return rows


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class DependenciesPanel(_BasePanel):
    """
    DjDT panel — URL-resolved request app + full dependency table.
    """

    title     = "Dependencies"
    nav_title = "Deps"
    template  = "dependency_map/panel.html"

    @property
    def scripts(self):
        from django.templatetags.static import static
        scripts = super().scripts
        scripts.append(static("dependency_map/js/panel.js"))
        return scripts

    def process_request(self, request):
        self._request_app: str | None = resolve_request_app(request)
        return self.get_response(request)

    def generate_stats(self, request, response):
        try:
            graph = _get_or_build_graph()
        except Exception:
            graph = {"apps": {}, "edges": [], "cycles": [], "stats": {}}

        request_apps_list = _collect_request_apps(self._request_app, graph)
        request_apps = set(request_apps_list)

        request_rows = _build_app_rows(graph, request_apps_list, request_apps)
        all_rows     = _build_app_rows(graph, None, request_apps)

        full_graph_url = _build_full_graph_url(request_apps)
        s = graph.get("stats", {})

        self.record_stats({
            "request_app":        self._request_app,
            "request_apps":       sorted(request_apps),
            "request_app_count":  len(request_apps),
            "all_app_count":      len(graph.get("apps", {})),
            "request_rows":       request_rows,
            "all_rows":           all_rows,
            "cycle_count":        s.get("cycle_count", 0),
            "import_cycle_count": s.get("import_cycle_count", 0),
            "fk_cycle_count":     s.get("fk_cycle_count", 0),
            "violation_count":    s.get("violation_count", 0),
            "full_graph_url":     full_graph_url,
            "has_grimp":          s.get("has_grimp", False),
        })

    @property
    def nav_subtitle(self) -> str:
        try:
            s = self.get_stats()
            if not s:
                return ""
            n  = s.get("request_app_count", 0)
            cy = s.get("cycle_count", 0)
            vi = s.get("violation_count", 0)
            parts = [f"{n} app{'s' if n != 1 else ''}"]
            if cy:
                parts.append(f"{cy} cycle{'s' if cy != 1 else ''}")
            if vi:
                parts.append(f"{vi} violation{'s' if vi != 1 else ''}")
            return " · ".join(parts)
        except Exception:
            return ""

    @classmethod
    def get_urls(cls):
        from django.urls import path
        from dependency_map.views import DependencyMapVersionView
        return [
            path("depmap/",         cls._graph_page_view,          name="depmap_page"),
            path("depmap/refresh/", cls._graph_refresh_view,       name="depmap_refresh"),
            path("depmap/version/", DependencyMapVersionView.as_view(), name="depmap_version"),
        ]

    @staticmethod
    def _graph_page_view(request):
        from django.http import HttpResponse
        from dependency_map.views import _render_graph_page

        try:
            graph = _get_or_build_graph()
        except Exception as exc:
            return HttpResponse(
                f"<h1 style='font-family:monospace;color:#ef4444;padding:20px'>"
                f"Analysis failed</h1><pre style='padding:20px'>{exc}</pre>",
                status=500, content_type="text/html",
            )

        try:
            from django.urls import reverse
            refresh_url = reverse("djdt:depmap_refresh")
            version_url = reverse("djdt:depmap_version")
        except Exception:
            refresh_url = ""
            version_url = ""

        response = _render_graph_page(request, graph, refresh_url, version_url)
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @staticmethod
    def _graph_refresh_view(request):
        from django.http import JsonResponse
        from dependency_map.views import _render_graph_json
        invalidate_graph_cache()
        try:
            graph = _get_or_build_graph()
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)
        return _render_graph_json(graph)


def _build_full_graph_url(request_apps: set[str]) -> str | None:
    qs = "?highlight=" + ",".join(sorted(request_apps)) if request_apps else ""
    for name in ("djdt:depmap_page", "dependency_map:index"):
        try:
            from django.urls import reverse
            return reverse(name) + qs
        except Exception:
            pass
    return None


# Backwards-compatibility alias.
DependencyMapPanel = DependenciesPanel
