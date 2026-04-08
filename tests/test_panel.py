"""
tests/test_panel.py
~~~~~~~~~~~~~~~~~~~
Tests for dependency_map.panels.DependenciesPanel.

Covers:
  - resolve_request_app(): URL resolution → app label mapping
  - _module_to_app(): single module → app label
  - _collect_request_apps(): graph walk from resolved app
  - _build_app_rows(): table row construction from graph data
  - highlight_apps rendering in render_html
  - DependenciesPanel.generate_stats() end-to-end
"""
from __future__ import annotations

import json
import sys
import types

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_GRAPH = {
    "apps": {
        "billing": {
            "name": "billing", "models": ["Invoice"], "model_count": 1,
            "in_degree": 0, "out_degree": 1, "in_cycle": False,
            "in_import_cycle": False, "in_fk_cycle": False,
            "is_third_party": False, "cycle_index": -1,
        },
        "core": {
            "name": "core", "models": ["Currency"], "model_count": 1,
            "in_degree": 1, "out_degree": 0, "in_cycle": False,
            "in_import_cycle": False, "in_fk_cycle": False,
            "is_third_party": False, "cycle_index": -1,
        },
        "django_contrib_auth": {
            "name": "django_contrib_auth", "models": ["User"], "model_count": 1,
            "in_degree": 2, "out_degree": 0, "in_cycle": False,
            "in_import_cycle": False, "in_fk_cycle": False,
            "is_third_party": True, "cycle_index": -1,
        },
    },
    "edges": [
        {
            "source": "billing", "target": "core",
            "types": ["import"], "coupling": "import",
            "violation": False, "model_edges": [],
            "in_import_cycle": False, "in_fk_cycle": False,
            "in_cycle": False, "cycle_index": -1,
        },
        {
            "source": "billing", "target": "django_contrib_auth",
            "types": ["fk"], "coupling": "fk",
            "violation": False, "model_edges": [{"from": "Invoice", "to": "User", "label": "owner"}],
            "in_import_cycle": False, "in_fk_cycle": False,
            "in_cycle": False, "cycle_index": -1,
        },
    ],
    "cycles": [],
    "direct_import_cycles": [],
    "direct_fk_cycles": [],
    "stats": {
        "app_count": 3, "edge_count": 2,
        "import_only_count": 1, "fk_only_count": 1,
        "both_count": 0, "violation_count": 0,
        "cycle_count": 0, "import_cycle_count": 0,
        "fk_cycle_count": 0, "cyclic_app_count": 0,
        "has_grimp": True,
    },
}

CYCLE_GRAPH = {
    "apps": {
        "billing": {
            "name": "billing", "models": [], "model_count": 0,
            "in_degree": 1, "out_degree": 1, "in_cycle": True,
            "in_import_cycle": True, "in_fk_cycle": False,
            "is_third_party": False, "cycle_index": 0,
        },
        "payments": {
            "name": "payments", "models": [], "model_count": 0,
            "in_degree": 1, "out_degree": 1, "in_cycle": True,
            "in_import_cycle": True, "in_fk_cycle": False,
            "is_third_party": False, "cycle_index": 0,
        },
    },
    "edges": [
        {
            "source": "billing", "target": "payments",
            "types": ["import"], "coupling": "import",
            "violation": False, "model_edges": [],
            "in_import_cycle": True, "in_fk_cycle": False,
            "in_cycle": True, "cycle_index": 0,
        },
        {
            "source": "payments", "target": "billing",
            "types": ["import"], "coupling": "import",
            "violation": False, "model_edges": [],
            "in_import_cycle": True, "in_fk_cycle": False,
            "in_cycle": True, "cycle_index": 0,
        },
    ],
    "cycles": [
        {"apps": ["billing", "payments"], "kind": "import",
         "label": "billing \u2194 payments", "example_path": "billing \u2192 payments \u2192 billing"},
    ],
    "direct_import_cycles": [{"a": "billing", "b": "payments", "label": "billing \u2194 payments"}],
    "direct_fk_cycles": [],
    "stats": {
        "app_count": 2, "edge_count": 2,
        "import_only_count": 2, "fk_only_count": 0,
        "both_count": 0, "violation_count": 0,
        "cycle_count": 1, "import_cycle_count": 1,
        "fk_cycle_count": 0, "cyclic_app_count": 2,
        "has_grimp": True,
    },
}


# ---------------------------------------------------------------------------
# _module_to_app()
# ---------------------------------------------------------------------------

class TestModuleToApp:
    """Tests for the single-module → app label mapping."""

    def test_exact_match(self):
        from unittest.mock import patch
        from dependency_map.panels import _module_to_app

        mapping = {"apps.billing": "billing", "apps.core": "core"}
        with patch("dependency_map.panels._build_prefix_map", return_value=mapping):
            assert _module_to_app("apps.billing") == "billing"

    def test_submodule_match(self):
        from unittest.mock import patch
        from dependency_map.panels import _module_to_app

        mapping = {"apps.billing": "billing"}
        with patch("dependency_map.panels._build_prefix_map", return_value=mapping):
            assert _module_to_app("apps.billing.views") == "billing"

    def test_unknown_module_returns_none(self):
        from unittest.mock import patch
        from dependency_map.panels import _module_to_app

        mapping = {"apps.billing": "billing"}
        with patch("dependency_map.panels._build_prefix_map", return_value=mapping):
            assert _module_to_app("rest_framework.views") is None

    def test_longest_prefix_wins(self):
        from unittest.mock import patch
        from dependency_map.panels import _module_to_app

        sorted_map = {
            "apps.billing.sub_app": "sub_app",
            "apps.billing": "billing",
        }
        with patch("dependency_map.panels._build_prefix_map", return_value=sorted_map):
            assert _module_to_app("apps.billing.sub_app.views") == "sub_app"

    def test_empty_string(self):
        from unittest.mock import patch
        from dependency_map.panels import _module_to_app

        mapping = {"apps.billing": "billing"}
        with patch("dependency_map.panels._build_prefix_map", return_value=mapping):
            assert _module_to_app("") is None


# ---------------------------------------------------------------------------
# resolve_request_app()
# ---------------------------------------------------------------------------

class TestResolveRequestApp:

    def test_resolves_view_to_app(self):
        from unittest.mock import MagicMock, patch
        from dependency_map.panels import resolve_request_app

        request = MagicMock()
        request.path = "/billing/invoices/"

        mock_match = MagicMock()
        mock_match.func.__module__ = "apps.billing.views"

        with patch("django.urls.resolve", return_value=mock_match), \
             patch("dependency_map.panels._module_to_app", return_value="billing"):
            assert resolve_request_app(request) == "billing"

    def test_resolver_404_returns_none(self):
        from unittest.mock import MagicMock, patch
        from django.urls import Resolver404
        from dependency_map.panels import resolve_request_app

        request = MagicMock()
        request.path = "/nonexistent/"

        with patch("django.urls.resolve", side_effect=Resolver404):
            assert resolve_request_app(request) is None

    def test_no_module_attr_returns_none(self):
        from unittest.mock import MagicMock, patch
        from dependency_map.panels import resolve_request_app

        request = MagicMock()
        request.path = "/something/"

        mock_match = MagicMock()
        mock_match.func = object()  # no __module__

        with patch("django.urls.resolve", return_value=mock_match):
            result = resolve_request_app(request)
            # object() has no __module__ → None
            assert result is None


# ---------------------------------------------------------------------------
# _collect_request_apps()
# ---------------------------------------------------------------------------

class TestCollectRequestApps:

    def test_includes_resolved_app_and_imports(self):
        from dependency_map.panels import _collect_request_apps

        result = _collect_request_apps("billing", MINIMAL_GRAPH)
        assert "billing" in result
        assert "core" in result  # billing imports core

    def test_does_not_include_fk_only_deps(self):
        from dependency_map.panels import _collect_request_apps

        result = _collect_request_apps("billing", MINIMAL_GRAPH)
        # django_contrib_auth is FK-only, not an import dependency
        assert "django_contrib_auth" not in result

    def test_none_app_returns_empty(self):
        from dependency_map.panels import _collect_request_apps

        assert _collect_request_apps(None, MINIMAL_GRAPH) == []

    def test_unknown_app_returns_itself(self):
        from dependency_map.panels import _collect_request_apps

        result = _collect_request_apps("nonexistent", MINIMAL_GRAPH)
        assert result == ["nonexistent"]

    def test_app_with_no_imports(self):
        from dependency_map.panels import _collect_request_apps

        result = _collect_request_apps("core", MINIMAL_GRAPH)
        assert result == ["core"]


# ---------------------------------------------------------------------------
# _build_app_rows()
# ---------------------------------------------------------------------------

class TestBuildAppRows:

    def test_outgoing_import_edges(self):
        from dependency_map.panels import _build_app_rows

        rows = {r["name"]: r for r in _build_app_rows(MINIMAL_GRAPH, None, set())}
        assert "core" in rows["billing"]["imports_from"]

    def test_incoming_import_edges(self):
        from dependency_map.panels import _build_app_rows

        rows = {r["name"]: r for r in _build_app_rows(MINIMAL_GRAPH, None, set())}
        assert "billing" in rows["core"]["imported_by"]

    def test_fk_targets(self):
        from dependency_map.panels import _build_app_rows

        rows = {r["name"]: r for r in _build_app_rows(MINIMAL_GRAPH, None, set())}
        assert "django_contrib_auth" in rows["billing"]["fk_targets"]

    def test_scope_apps_filters(self):
        """When scope_apps is given, only those apps appear as rows."""
        from dependency_map.panels import _build_app_rows

        rows = _build_app_rows(MINIMAL_GRAPH, ["billing"], set())
        assert len(rows) == 1
        assert rows[0]["name"] == "billing"

    def test_is_request_flag(self):
        from dependency_map.panels import _build_app_rows

        rows = {r["name"]: r for r in _build_app_rows(MINIMAL_GRAPH, None, {"billing"})}
        assert rows["billing"]["is_request"] is True
        assert rows["core"]["is_request"] is False

    def test_third_party_flag(self):
        from dependency_map.panels import _build_app_rows

        rows = {r["name"]: r for r in _build_app_rows(MINIMAL_GRAPH, None, set())}
        assert rows["django_contrib_auth"]["is_third_party"] is True
        assert rows["billing"]["is_third_party"] is False

    def test_cycle_detection(self):
        from dependency_map.panels import _build_app_rows

        rows = {r["name"]: r for r in _build_app_rows(CYCLE_GRAPH, None, set())}
        assert rows["billing"]["in_cycle"] is True
        assert rows["billing"]["cycle_kind"] == "import"
        assert "billing" in rows["billing"]["cycle_label"]
        assert "payments" in rows["billing"]["cycle_label"]

    def test_no_cycle(self):
        from dependency_map.panels import _build_app_rows

        rows = {r["name"]: r for r in _build_app_rows(MINIMAL_GRAPH, None, set())}
        assert rows["billing"]["in_cycle"] is False
        assert rows["billing"]["cycle_kind"] == ""

    def test_empty_graph(self):
        from dependency_map.panels import _build_app_rows

        empty = {"apps": {}, "edges": [], "cycles": [], "stats": {}}
        rows = _build_app_rows(empty, None, set())
        assert rows == []


# ---------------------------------------------------------------------------
# render_html highlight_apps
# ---------------------------------------------------------------------------

class TestRenderHighlight:

    GRAPH = {
        "apps": {
            "billing": {"name": "billing", "models": [], "model_count": 0,
                        "in_degree": 0, "out_degree": 0,
                        "in_cycle": False, "in_import_cycle": False, "in_fk_cycle": False,
                        "is_third_party": False, "cycle_index": -1},
        },
        "edges": [], "cycles": [],
        "direct_import_cycles": [], "direct_fk_cycles": [],
        "stats": {
            "app_count": 1, "edge_count": 0, "import_only_count": 0,
            "fk_only_count": 0, "both_count": 0, "violation_count": 0,
            "cycle_count": 0, "import_cycle_count": 0, "fk_cycle_count": 0,
            "cyclic_app_count": 0, "has_grimp": True,
        },
    }

    def test_no_highlight_embeds_empty_list(self):
        from dependency_map.renderer import render_html

        html = render_html(self.GRAPH)
        assert "const HIGHLIGHT_APPS = []" in html

    def test_highlight_apps_embedded(self):
        from dependency_map.renderer import render_html

        html = render_html(self.GRAPH, highlight_apps=["billing", "core"])
        assert '"billing"' in html
        assert '"core"' in html
        assert 'const HIGHLIGHT_APPS = ["billing", "core"]' in html

    def test_placeholder_fully_replaced(self):
        from dependency_map.renderer import render_html

        html = render_html(self.GRAPH, highlight_apps=["billing"])
        assert "__HIGHLIGHT_APPS__" not in html

    def test_write_html_passes_highlight(self, tmp_path):
        from dependency_map.renderer import write_html

        out = tmp_path / "map.html"
        write_html(self.GRAPH, out, highlight_apps=["users"])
        content = out.read_text()
        assert '"users"' in content
        assert "__HIGHLIGHT_APPS__" not in content


# ---------------------------------------------------------------------------
# DependenciesPanel.generate_stats()
# ---------------------------------------------------------------------------

class TestDependenciesPanelStats:
    """Integration test for the panel's generate_stats method."""

    def test_generate_stats_populates_request_app(self):
        """The resolved request app appears in stats."""
        from unittest.mock import MagicMock, patch
        from dependency_map.panels import DependenciesPanel

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        toolbar = MagicMock()
        toolbar.stats = {}
        toolbar.store.save_panel = MagicMock()

        panel = DependenciesPanel(toolbar=toolbar, get_response=get_response)
        panel._request_app = "billing"

        request  = MagicMock()
        response = MagicMock(status_code=200)

        with patch("dependency_map.panels._get_or_build_graph", return_value=MINIMAL_GRAPH), \
             patch("dependency_map.panels._build_full_graph_url", return_value="/depmap/?highlight=billing,core"):
            panel.generate_stats(request, response)

        recorded = toolbar.stats.get(panel.panel_id, {})
        assert recorded.get("request_app") == "billing"
        assert "billing" in recorded.get("request_apps", [])
        assert "core" in recorded.get("request_apps", [])  # billing imports core

    def test_generate_stats_includes_all_rows(self):
        """all_rows should cover all apps in the graph."""
        from unittest.mock import MagicMock, patch
        from dependency_map.panels import DependenciesPanel

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        toolbar = MagicMock()
        toolbar.stats = {}
        toolbar.store.save_panel = MagicMock()

        panel = DependenciesPanel(toolbar=toolbar, get_response=get_response)
        panel._request_app = None

        request = response = MagicMock()

        with patch("dependency_map.panels._get_or_build_graph", return_value=MINIMAL_GRAPH), \
             patch("dependency_map.panels._build_full_graph_url", return_value=None):
            panel.generate_stats(request, response)

        recorded  = toolbar.stats.get(panel.panel_id, {})
        all_names = [r["name"] for r in recorded.get("all_rows", [])]
        assert "billing" in all_names
        assert "core"    in all_names

    def test_generate_stats_cycle_info_in_rows(self):
        """Cycle information from the graph is reflected in row data."""
        from unittest.mock import MagicMock, patch
        from dependency_map.panels import DependenciesPanel

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        toolbar = MagicMock()
        toolbar.stats = {}
        toolbar.store.save_panel = MagicMock()

        panel = DependenciesPanel(toolbar=toolbar, get_response=get_response)
        panel._request_app = "billing"

        request = response = MagicMock()

        with patch("dependency_map.panels._get_or_build_graph", return_value=CYCLE_GRAPH), \
             patch("dependency_map.panels._build_full_graph_url", return_value=None):
            panel.generate_stats(request, response)

        recorded  = toolbar.stats.get(panel.panel_id, {})
        rows      = {r["name"]: r for r in recorded.get("all_rows", [])}
        assert rows["billing"]["in_cycle"] is True
        assert recorded["cycle_count"] == 1

    def test_graph_failure_does_not_raise(self):
        """A broken graph cache should not crash generate_stats."""
        from unittest.mock import MagicMock, patch
        from dependency_map.panels import DependenciesPanel

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        toolbar = MagicMock()
        toolbar.stats = {}
        toolbar.store.save_panel = MagicMock()

        panel = DependenciesPanel(toolbar=toolbar, get_response=get_response)
        panel._request_app = "billing"

        request = response = MagicMock()

        with patch("dependency_map.panels._get_or_build_graph", side_effect=RuntimeError("boom")), \
             patch("dependency_map.panels._build_full_graph_url", return_value=None):
            # Should not raise
            panel.generate_stats(request, response)

    def test_none_request_app_still_works(self):
        """When URL resolution fails, panel still generates stats."""
        from unittest.mock import MagicMock, patch
        from dependency_map.panels import DependenciesPanel

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        toolbar = MagicMock()
        toolbar.stats = {}
        toolbar.store.save_panel = MagicMock()

        panel = DependenciesPanel(toolbar=toolbar, get_response=get_response)
        panel._request_app = None

        request = response = MagicMock()

        with patch("dependency_map.panels._get_or_build_graph", return_value=MINIMAL_GRAPH), \
             patch("dependency_map.panels._build_full_graph_url", return_value=None):
            panel.generate_stats(request, response)

        recorded = toolbar.stats.get(panel.panel_id, {})
        assert recorded.get("request_app") is None
        assert recorded.get("request_apps") == []
        assert recorded.get("request_app_count") == 0
