"""
Tests for django-dependency-map.

Run with:  pytest
"""
from __future__ import annotations

import tempfile
import os
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# cycles.py
# ---------------------------------------------------------------------------


class TestCycleDetection:
    from dependency_map.cycles import find_cycles, annotate_graph

    def _edges(self, pairs, type_="import"):
        return [
            {"source": s, "target": t, "types": [type_], "coupling": type_, "violation": False, "model_edges": []}
            for s, t in pairs
        ]

    def test_no_cycles(self):
        from dependency_map.cycles import find_cycles
        edges = self._edges([("a", "b"), ("b", "c"), ("a", "c")])
        assert find_cycles(edges) == []

    def test_simple_cycle(self):
        from dependency_map.cycles import find_cycles
        edges = self._edges([("a", "b"), ("b", "c"), ("c", "a")])
        cycles = find_cycles(edges)
        assert len(cycles) == 1
        assert set(cycles[0].apps) == {"a", "b", "c"}

    def test_self_loop_not_reported(self):
        from dependency_map.cycles import find_cycles
        # Single-node SCCs are excluded
        edges = self._edges([("a", "b"), ("b", "a")])
        cycles = find_cycles(edges)
        assert len(cycles) == 1  # a↔b is a 2-node SCC

    def test_fk_edges_ignored(self):
        from dependency_map.cycles import find_cycles
        # FK-only edges should not contribute to cycles
        edges = self._edges([("a", "b"), ("b", "a")], type_="fk")
        cycles = find_cycles(edges)
        assert cycles == []

    def test_annotate_flags_apps_and_edges(self):
        from dependency_map.cycles import find_cycles, annotate_graph
        edges = self._edges([("a", "b"), ("b", "c"), ("c", "a"), ("d", "a")])
        graph = {
            "apps": {n: {"name": n} for n in "abcd"},
            "edges": edges,
            "stats": {},
        }
        cycles = find_cycles(edges)
        annotate_graph(graph, cycles)

        assert graph["apps"]["a"]["in_cycle"] is True
        assert graph["apps"]["d"]["in_cycle"] is False
        assert graph["stats"]["cycle_count"] == 1
        assert graph["stats"]["cyclic_app_count"] == 3

        cycle_edges = [e for e in graph["edges"] if e["in_cycle"]]
        # a→b, b→c, c→a are in the cycle; d→a is not
        assert len(cycle_edges) == 3


# ---------------------------------------------------------------------------
# importlinter.py
# ---------------------------------------------------------------------------


class TestImportLinterParser:

    def _write_config(self, content: str) -> str:
        tmpdir = tempfile.mkdtemp()
        Path(tmpdir, ".importlinter").write_text(content)
        return tmpdir

    def test_layers_upward_imports_are_violations(self):
        from dependency_map.importlinter import load_violations
        tmpdir = self._write_config("""\
[importlinter]
root_package = myproject

[importlinter:contract:1]
name = Layers
type = layers
layers =
    billing
    users
    core
""")
        violations = load_violations(tmpdir)
        # Lower layers importing upper layers are violations
        assert ("users", "billing") in violations
        assert ("core", "billing") in violations
        assert ("core", "users") in violations
        # Upper importing lower is fine — should NOT be in violations
        assert ("billing", "users") not in violations

    def test_independence(self):
        from dependency_map.importlinter import load_violations
        tmpdir = self._write_config("""\
[importlinter]
root_package = myproject

[importlinter:contract:1]
name = Independence
type = independence
modules =
    myproject.webhooks
    myproject.notifications
""")
        violations = load_violations(tmpdir)
        assert ("webhooks", "notifications") in violations
        assert ("notifications", "webhooks") in violations

    def test_forbidden(self):
        from dependency_map.importlinter import load_violations
        tmpdir = self._write_config("""\
[importlinter]
root_package = myproject

[importlinter:contract:1]
name = Forbidden
type = forbidden
source_modules =
    myproject.core
forbidden_modules =
    myproject.billing
    myproject.accounts
""")
        violations = load_violations(tmpdir)
        assert ("core", "billing") in violations
        assert ("core", "accounts") in violations
        assert ("billing", "core") not in violations

    def test_missing_file_returns_empty(self):
        from dependency_map.importlinter import load_violations
        with tempfile.TemporaryDirectory() as tmpdir:
            assert load_violations(tmpdir) == []

    def test_pipe_separated_layer_peers(self):
        from dependency_map.importlinter import load_violations
        tmpdir = self._write_config("""\
[importlinter]
root_package = myproject

[importlinter:contract:1]
name = Peers
type = layers
layers =
    billing | treasury
    core
""")
        violations = load_violations(tmpdir)
        # core must not import billing or treasury
        assert ("core", "billing") in violations
        assert ("core", "treasury") in violations
        # billing and treasury can import each other freely (same layer)
        assert ("billing", "treasury") not in violations


# ---------------------------------------------------------------------------
# renderer.py
# ---------------------------------------------------------------------------


class TestRenderer:

    MINIMAL_GRAPH = {
        "apps": {
            "billing": {"name": "billing", "models": ["Invoice"], "model_count": 1,
                        "in_degree": 0, "out_degree": 1, "in_cycle": False, "cycle_index": -1},
            "core":    {"name": "core",    "models": ["Currency"], "model_count": 1,
                        "in_degree": 1, "out_degree": 0, "in_cycle": False, "cycle_index": -1},
        },
        "edges": [
            {"source": "billing", "target": "core", "types": ["fk", "import"],
             "coupling": "both", "violation": False, "model_edges": [], "in_cycle": False, "cycle_index": -1},
        ],
        "cycles": [],
        "stats": {
            "app_count": 2, "edge_count": 1, "import_only_count": 0,
            "fk_only_count": 0, "both_count": 1, "violation_count": 0,
            "cycle_count": 0, "cyclic_app_count": 0, "has_grimp": True,
        },
    }

    def test_render_produces_html(self):
        from dependency_map.renderer import render_html
        html = render_html(self.MINIMAL_GRAPH, title="Test Map")
        assert html.startswith("<!DOCTYPE html>")
        assert "Test Map" in html

    def test_graph_json_embedded(self):
        from dependency_map.renderer import render_html
        html = render_html(self.MINIMAL_GRAPH)
        assert '"billing"' in html
        assert '"core"' in html

    def test_no_template_placeholders_left(self):
        from dependency_map.renderer import render_html
        html = render_html(self.MINIMAL_GRAPH)
        assert "__TITLE__" not in html
        assert "__GRAPH_JSON__" not in html
        assert "__COLORS_JSON__" not in html
        assert "__VERSION_URL__" not in html

    def test_version_url_embedded(self):
        from dependency_map.renderer import render_html
        html = render_html(self.MINIMAL_GRAPH, version_url="/depmap/version/")
        assert "const VERSION_URL" in html
        assert "/depmap/version/" in html

    def test_auto_refresh_polling_present(self):
        from dependency_map.renderer import render_html
        html = render_html(self.MINIMAL_GRAPH, version_url="/v/", refresh_url="/r/")
        assert "pollVersion" in html

    def test_write_html_creates_file(self, tmp_path):
        from dependency_map.renderer import write_html
        out = tmp_path / "map.html"
        write_html(self.MINIMAL_GRAPH, out)
        assert out.exists()
        assert out.stat().st_size > 10_000  # should be a substantial file


# ---------------------------------------------------------------------------
# App discovery
# ---------------------------------------------------------------------------


class TestDiscoverRootPackages:

    def test_returns_configured_setting(self):
        from unittest.mock import patch, MagicMock
        from dependency_map.analyzer import discover_root_packages

        with patch("django.conf.settings") as mock_settings:
            mock_settings.DEPENDENCY_MAP_ROOT_PACKAGES = ["myapp", "shared"]
            result = discover_root_packages()
        assert result == ["myapp", "shared"]

    def test_auto_discovers_from_app_registry(self):
        from unittest.mock import patch, MagicMock
        from pathlib import Path
        from dependency_map.analyzer import discover_root_packages

        cfg1 = MagicMock()
        cfg1.name = "billing"
        cfg1.module.__file__ = "/project/billing/__init__.py"

        cfg2 = MagicMock()
        cfg2.name = "myapp.core"
        cfg2.module.__file__ = "/project/myapp/core/__init__.py"

        # Third-party should be excluded
        cfg3 = MagicMock()
        cfg3.name = "django.contrib.auth"
        cfg3.module.__file__ = "/venv/site-packages/django/contrib/auth/__init__.py"

        with patch("django.conf.settings") as mock_settings, \
             patch("django.apps.apps.get_app_configs", return_value=[cfg1, cfg2, cfg3]):
            mock_settings.DEPENDENCY_MAP_ROOT_PACKAGES = None
            mock_settings.ROOT_URLCONF = "myapp.urls"
            result = discover_root_packages(project_dir=Path("/project"))

        assert "billing" in result
        assert "myapp" in result
        assert "django" not in result

    def test_falls_back_to_root_urlconf(self):
        from unittest.mock import patch, MagicMock
        from pathlib import Path
        from dependency_map.analyzer import discover_root_packages

        with patch("django.conf.settings") as mock_settings, \
             patch("django.apps.apps.get_app_configs", return_value=[]):
            mock_settings.DEPENDENCY_MAP_ROOT_PACKAGES = None
            mock_settings.ROOT_URLCONF = "myproject.urls"
            result = discover_root_packages(project_dir=Path("/nonexistent"))

        assert result == ["myproject"]


class TestBuildModuleToAppMap:

    def test_maps_apps_with_prefix_stripping(self):
        from unittest.mock import patch, MagicMock
        from dependency_map.analyzer import build_module_to_app_map

        cfg1 = MagicMock()
        cfg1.name = "apps.billing"
        cfg1.label = "apps_billing"

        cfg2 = MagicMock()
        cfg2.name = "apps.core"
        cfg2.label = "apps_core"

        with patch("django.apps.apps.get_app_configs", return_value=[cfg1, cfg2]):
            result = build_module_to_app_map(["apps"])

        assert result["apps.billing"] == "billing"
        assert result["apps.core"] == "core"

    def test_top_level_apps_keep_label(self):
        from unittest.mock import patch, MagicMock
        from dependency_map.analyzer import build_module_to_app_map

        cfg = MagicMock()
        cfg.name = "dboard"
        cfg.label = "dboard"

        with patch("django.apps.apps.get_app_configs", return_value=[cfg]):
            result = build_module_to_app_map(["test_project"])

        assert result["dboard"] == "dboard"

    def test_sorted_longest_first(self):
        from unittest.mock import patch, MagicMock
        from dependency_map.analyzer import build_module_to_app_map

        cfg1 = MagicMock()
        cfg1.name = "apps.billing"
        cfg1.label = "billing"

        cfg2 = MagicMock()
        cfg2.name = "apps.billing.sub"
        cfg2.label = "sub"

        with patch("django.apps.apps.get_app_configs", return_value=[cfg1, cfg2]):
            result = build_module_to_app_map([])

        keys = list(result.keys())
        assert keys.index("apps.billing.sub") < keys.index("apps.billing")


class TestModuleToApp:

    def test_exact_match(self):
        from dependency_map.analyzer import module_to_app
        app_map = {"dboard": "dboard", "billing": "billing"}
        assert module_to_app("dboard", app_map) == "dboard"

    def test_submodule_match(self):
        from dependency_map.analyzer import module_to_app
        app_map = {"dboard": "dboard"}
        assert module_to_app("dboard.models", app_map) == "dboard"

    def test_unknown_returns_none(self):
        from dependency_map.analyzer import module_to_app
        app_map = {"dboard": "dboard"}
        assert module_to_app("os.path", app_map) is None

    def test_longest_prefix_wins(self):
        from dependency_map.analyzer import module_to_app
        # Sorted longest-first
        app_map = {"apps.billing.sub": "sub", "apps.billing": "billing"}
        assert module_to_app("apps.billing.sub.views", app_map) == "sub"


class TestProcessImportGraphWithAppMap:
    """Verify that _process_import_graph uses app_map for module→app mapping."""

    def test_top_level_apps_detected(self):
        from unittest.mock import MagicMock, patch
        from dependency_map.analyzer import DependencyAnalyzer

        mock_graph = MagicMock()
        mock_graph.modules = [
            "dboard", "dboard.models", "dboard.views",
            "billing", "billing.models",
        ]
        mock_graph.find_modules_directly_imported_by.side_effect = lambda m: {
            "dboard.views": ["billing.models"],
        }.get(m, [])

        app_map = {"dboard": "dboard", "billing": "billing"}

        analyzer = DependencyAnalyzer(
            root_packages=["dboard", "billing"],
            app_map=app_map,
        )
        analyzer._process_import_graph(mock_graph, "dboard")

        assert ("dboard", "billing") in analyzer.edges
        assert "import" in analyzer.edges[("dboard", "billing")].types

    def test_nested_apps_detected(self):
        from unittest.mock import MagicMock
        from dependency_map.analyzer import DependencyAnalyzer

        mock_graph = MagicMock()
        mock_graph.modules = [
            "myproject.billing", "myproject.billing.views",
            "myproject.core", "myproject.core.models",
        ]
        mock_graph.find_modules_directly_imported_by.side_effect = lambda m: {
            "myproject.billing.views": ["myproject.core.models"],
        }.get(m, [])

        app_map = {"myproject.billing": "billing", "myproject.core": "core"}

        analyzer = DependencyAnalyzer(
            root_packages=["myproject"],
            app_map=app_map,
        )
        analyzer._process_import_graph(mock_graph, "myproject")

        assert ("billing", "core") in analyzer.edges

    def test_legacy_fallback_without_app_map(self):
        """Without app_map, the old parts[1] logic is used."""
        from unittest.mock import MagicMock
        from dependency_map.analyzer import DependencyAnalyzer

        mock_graph = MagicMock()
        mock_graph.modules = [
            "myproject.billing", "myproject.billing.views",
            "myproject.core", "myproject.core.models",
        ]
        mock_graph.find_modules_directly_imported_by.side_effect = lambda m: {
            "myproject.billing.views": ["myproject.core.models"],
        }.get(m, [])

        analyzer = DependencyAnalyzer(
            root_packages=["myproject"],
            app_map=None,
        )
        analyzer._process_import_graph(mock_graph, "myproject")

        assert ("billing", "core") in analyzer.edges


# ---------------------------------------------------------------------------
# DOT parsing — abstract model deduplication
# ---------------------------------------------------------------------------


class TestAbstractModelDeduplication:
    """
    graph_models --group-models duplicates abstract base model nodes into
    every cluster that inherits from them.  _parse_dot must attribute these
    nodes to their true app (derived from the node ID prefix), not the
    inheriting cluster.
    """

    # Minimal DOT: two clusters (cashback, cards) both containing
    # apps_core_models_BaseModel.  cashback has an FK to a cards model.
    DOT = """\
digraph model_graph {
  subgraph cluster_apps_cashback {
    apps_core_models_BaseModel [label=<
      <TABLE><TR><TD><B>BaseModel</B></TD></TR></TABLE>>]
    apps_cashback_models_CashbackConfig [label=<
      <TABLE><TR><TD><B>CashbackConfig</B></TD></TR></TABLE>>]
  }
  subgraph cluster_apps_cards {
    apps_core_models_BaseModel [label=<
      <TABLE><TR><TD><B>BaseModel</B></TD></TR></TABLE>>]
    apps_cards_models_Card [label=<
      <TABLE><TR><TD><B>Card</B></TD></TR></TABLE>>]
  }
  apps_cashback_models_CashbackConfig -> apps_cards_models_Card
  [label=" card (cashback_configs)"] [arrowhead=none, arrowtail=dot, dir=both];
  apps_cashback_models_CashbackConfig -> apps_core_models_BaseModel
  [label=" abstract inheritance"] [arrowhead=empty, arrowtail=none, dir=both];
  apps_cards_models_Card -> apps_core_models_BaseModel
  [label=" abstract inheritance"] [arrowhead=empty, arrowtail=none, dir=both];
}
"""

    def _make_analyzer(self):
        from dependency_map.analyzer import DependencyAnalyzer
        a = DependencyAnalyzer(
            root_packages=["apps"],
            app_map={
                "apps.cashback": "cashback",
                "apps.cards": "cards",
                "apps.core": "core",
            },
        )
        return a

    def test_no_false_cards_to_cashback_edge(self):
        """The only FK edge should be cashback → cards, not the reverse."""
        a = self._make_analyzer()
        a._parse_dot(self.DOT)
        assert ("cashback", "cards") in a.edges
        assert ("cards", "cashback") not in a.edges

    def test_abstract_model_not_in_inheriting_apps(self):
        """BaseModel should not appear in the model list of cashback or cards."""
        a = self._make_analyzer()
        a._parse_dot(self.DOT)
        assert "BaseModel" not in a.app_nodes["cashback"].models
        assert "BaseModel" not in a.app_nodes["cards"].models

    def test_foreign_abstract_model_excluded_from_node_map(self):
        """
        Foreign abstract model nodes should be excluded from node_to_app
        entirely so that inherited FK edges (e.g. BaseModel.created_by)
        don't create phantom app-level dependencies.
        """
        a = self._make_analyzer()
        a._parse_dot(self.DOT)
        edge_apps = {(e.source, e.target) for e in a.edges.values()}
        # Only the real FK: cashback → cards.  No edges involving 'core'.
        assert edge_apps == {("cashback", "cards")}

    def test_foreign_abstract_fk_edges_dropped(self):
        """
        An FK on a foreign abstract model (e.g. BaseModel.created_by → User)
        should not create any app-level edge, since the node is excluded
        from the mapping.
        """
        dot_with_fk = self.DOT.replace(
            "}\n",
            "  apps_core_models_BaseModel -> apps_users_models_User\n"
            '  [label=" created_by"] [arrowhead=none, arrowtail=dot, dir=both];\n'
            "}\n",
            1,  # replace only the final closing brace
        )
        a = self._make_analyzer()
        a._parse_dot(dot_with_fk)
        edge_apps = {(e.source, e.target) for e in a.edges.values()}
        # BaseModel → User FK should be dropped, not appear as core → users
        assert "core" not in {app for pair in edge_apps for app in pair}


# ---------------------------------------------------------------------------
# Auto-refresh version endpoint
# ---------------------------------------------------------------------------


class TestProcessEpoch:

    def test_epoch_is_a_number(self):
        from dependency_map.views import _PROCESS_EPOCH
        assert isinstance(_PROCESS_EPOCH, float)
        assert _PROCESS_EPOCH > 0

    def test_version_view_returns_epoch(self):
        from unittest.mock import MagicMock
        from dependency_map.views import DependencyMapVersionView

        request = MagicMock()
        view = DependencyMapVersionView()
        response = view.get(request)

        import json
        data = json.loads(response.content)
        assert "epoch" in data
        assert isinstance(data["epoch"], float)
        assert response["Cache-Control"] == "no-store"


# ---------------------------------------------------------------------------
# Grimp cache behaviour
# ---------------------------------------------------------------------------


class TestGrimpCacheBehaviour:
    """
    Verify that the live view always bypasses grimp's file-based .grimp_cache,
    while the management command subprocess is free to use it.

    grimp's default (cache_dir=NotSupplied) resolves to writing/reading a
    .grimp_cache/ directory.  Passing cache_dir=None disables this entirely
    and forces a full filesystem scan — which is what the live view needs so
    that adding or removing an import is reflected immediately on refresh.
    """

    def _run_analyze_imports(self, disable_grimp_cache: bool) -> dict:
        """Run _analyze_imports with a patched grimp and return captured kwargs."""
        from unittest.mock import MagicMock, patch
        from dependency_map.analyzer import DependencyAnalyzer

        captured: list[dict] = []

        def fake_build_graph(package, **kwargs):
            captured.append(kwargs)
            mock_graph = MagicMock()
            mock_graph.modules = []
            return mock_graph

        with patch("grimp.build_graph", side_effect=fake_build_graph):
            a = DependencyAnalyzer(
                root_packages=["myproject"],
                disable_grimp_cache=disable_grimp_cache,
            )
            a._analyze_imports()

        assert len(captured) == 1, "build_graph should have been called once"
        return captured[0]

    def test_disable_grimp_cache_true_passes_cache_dir_none(self):
        """
        When disable_grimp_cache=True, grimp.build_graph must receive
        cache_dir=None so it skips the .grimp_cache directory entirely.
        """
        kwargs = self._run_analyze_imports(disable_grimp_cache=True)
        assert kwargs.get("cache_dir") is None, (
            f"Expected cache_dir=None but got {kwargs.get('cache_dir')!r}. "
            "The live view will serve stale import data."
        )

    def test_disable_grimp_cache_false_omits_cache_dir(self):
        """
        When disable_grimp_cache=False (management command default), grimp's
        own default cache behaviour should be left intact — cache_dir must
        not be overridden.
        """
        kwargs = self._run_analyze_imports(disable_grimp_cache=False)
        assert "cache_dir" not in kwargs, (
            f"Expected cache_dir to be absent but got {kwargs!r}. "
            "The management command should use grimp's default file cache."
        )

    def test_run_analysis_defaults_disable_grimp_cache_true(self):
        """
        _run_analysis() — the function called by both the Django view and the
        Debug Toolbar panel — must default to disable_grimp_cache=True so that
        all live paths bypass the file cache without needing explicit opt-in.
        """
        import inspect
        from dependency_map.views import _run_analysis

        sig = inspect.signature(_run_analysis)
        default = sig.parameters["disable_grimp_cache"].default
        assert default is True, (
            f"_run_analysis disable_grimp_cache default should be True, got {default!r}. "
            "Live views will serve stale data if this regresses to False."
        )
