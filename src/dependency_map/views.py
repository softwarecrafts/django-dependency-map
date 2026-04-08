"""
dependency_map.views
~~~~~~~~~~~~~~~~~~~~
Serves the dependency map as a live Django page.

Usage — add to your project's URLconf::

    # urls.py
    from django.urls import include, path

    urlpatterns = [
        ...
        path("__depmap__/", include("dependency_map.urls")),
    ]

Then visit /__depmap__/ in your browser (staff-only by default).

Settings
--------
DEPENDENCY_MAP_STAFF_ONLY
    Default: True. Set to False to allow any authenticated user (or remove
    auth entirely — be careful in production).

DEPENDENCY_MAP_ROOT_PACKAGES
    List of root Python packages passed to grimp. Auto-detected from
    ROOT_URLCONF when not set.

DEPENDENCY_MAP_TITLE
    Page title. Defaults to "<project> — Dependency Map".
"""
from __future__ import annotations

import time

from django.conf import settings as django_settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin

# Set once when this module is first imported in a new process.
# Every runserver restart produces a new value.
_PROCESS_EPOCH = time.time()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _staff_only() -> bool:
    return bool(getattr(django_settings, "DEPENDENCY_MAP_STAFF_ONLY", True))


def _check_access(request) -> HttpResponse | None:
    """Return an error response if the request should be denied, else None."""
    if _staff_only() and not getattr(request.user, "is_staff", False):
        return HttpResponse(
            "<h1>403 — Staff only</h1>"
            "<p>Set <code>DEPENDENCY_MAP_STAFF_ONLY = False</code> in settings to open access.</p>",
            status=403,
            content_type="text/html",
        )
    return None


def _get_root_packages() -> list[str]:
    from dependency_map.analyzer import discover_root_packages
    return discover_root_packages()


def _get_app_map(root_packages: list[str]) -> dict[str, str]:
    from dependency_map.analyzer import build_module_to_app_map
    return build_module_to_app_map(root_packages)


def _get_valid_app_labels(root_packages: list[str]) -> set[str] | None:
    """
    Build the set of real app labels from the canonical module→app mapping.
    """
    try:
        app_map = _get_app_map(root_packages)
        return set(app_map.values())
    except Exception:
        return None


def _page_title() -> str:
    configured = getattr(django_settings, "DEPENDENCY_MAP_TITLE", None)
    if configured:
        return configured
    urlconf = getattr(django_settings, "ROOT_URLCONF", "")
    project = urlconf.split(".")[0] if urlconf and "." in urlconf else "Django"
    return f"{project} — Dependency Map"


def _run_analysis(
    root_packages: list[str],
    valid_app_labels: set[str] | None,
    disable_grimp_cache: bool = True,
) -> dict:
    from dependency_map.analyzer import DependencyAnalyzer, build_module_to_app_map

    try:
        app_map = build_module_to_app_map(root_packages)
    except Exception:
        app_map = None

    analyzer = DependencyAnalyzer(
        root_packages=root_packages,
        valid_app_labels=valid_app_labels,
        # Default True for live views — bypasses grimp's .grimp_cache so that
        # any .py changes are always picked up. The management command subprocess
        # leaves this False so it can benefit from the cache.
        disable_grimp_cache=disable_grimp_cache,
        app_map=app_map,
    )
    return analyzer.analyze()


# ---------------------------------------------------------------------------
# Shared response builders
# ---------------------------------------------------------------------------

def _render_graph_page(request, graph, refresh_url, version_url):
    """Build the full HTML response for the D3 graph page."""
    from dependency_map.renderer import render_html

    highlight_apps = [
        a.strip()
        for a in request.GET.get("highlight", "").split(",")
        if a.strip()
    ]

    html = render_html(
        graph,
        title=_page_title(),
        refresh_url=refresh_url,
        version_url=version_url,
        highlight_apps=highlight_apps or None,
    )
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response


def _render_graph_json(graph):
    """Build the JSON response for a graph refresh."""
    return JsonResponse(graph)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@method_decorator(xframe_options_sameorigin, name="dispatch")
class DependencyMapView(View):
    """Renders the full interactive HTML page."""

    def get(self, request):
        denied = _check_access(request)
        if denied:
            return denied

        root_packages  = _get_root_packages()
        valid_app_labels = _get_valid_app_labels(root_packages)

        try:
            graph = _run_analysis(root_packages, valid_app_labels)
        except Exception as exc:
            return HttpResponse(
                f"<h1>Analysis failed</h1><pre>{exc}</pre>",
                status=500, content_type="text/html",
            )

        base = request.path.rstrip("/")
        return _render_graph_page(
            request, graph,
            refresh_url=base + "/refresh/",
            version_url=base + "/version/",
        )


class DependencyMapVersionView(View):
    """Tiny endpoint returning the process epoch — used for auto-refresh polling."""

    def get(self, request):
        response = JsonResponse({"epoch": _PROCESS_EPOCH})
        response["Cache-Control"] = "no-store"
        return response


@method_decorator(xframe_options_sameorigin, name="dispatch")
class DependencyMapRefreshView(View):
    """JSON endpoint that re-runs the analysis and returns fresh graph data."""

    def get(self, request):
        denied = _check_access(request)
        if denied:
            return JsonResponse({"error": "Forbidden"}, status=403)

        root_packages    = _get_root_packages()
        valid_app_labels = _get_valid_app_labels(root_packages)

        try:
            graph = _run_analysis(root_packages, valid_app_labels)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)

        return _render_graph_json(graph)
