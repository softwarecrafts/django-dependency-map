"""
dependency_map.analyzer
~~~~~~~~~~~~~~~~~~~~~~~
Merges two sources of Django dependency data:
  1. graph_models (django-extensions) → model-level FK/M2M relationships
  2. grimp → actual Python import relationships between apps

Produces a unified graph dict ready for rendering.

Real graph_models DOT format (with --group-models):
  - Node IDs:  billing_models_Invoice  (unquoted, underscores)
  - Node labels: HTML tables with <B>ModelName</B>
  - Edges span TWO lines:
      billing_models_Invoice -> accounts_models_User
      [label=" customer (invoice)"] [arrowhead=none, ...];
  - Clusters: subgraph cluster_billing { ... }
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import grimp
    HAS_GRIMP = True
except ImportError:
    HAS_GRIMP = False

from dependency_map.cycles import find_cycles, annotate_graph
from dependency_map import importlinter as _importlinter


# ---------------------------------------------------------------------------
# App discovery — auto-detect root packages and module→app mapping
# ---------------------------------------------------------------------------

def discover_root_packages(project_dir: Path | None = None) -> list[str]:
    """
    Auto-detect root packages to scan by inspecting Django's app registry.

    Filters out third-party apps (those whose source lives in site-packages)
    and returns the unique top-level package names.  Merges with any explicit
    ``DEPENDENCY_MAP_ROOT_PACKAGES`` setting.
    """
    from django.conf import settings as django_settings

    configured = getattr(django_settings, "DEPENDENCY_MAP_ROOT_PACKAGES", None)
    if configured:
        return list(configured)

    base_dir = project_dir or Path.cwd()
    packages: set[str] = set()

    for cfg in _get_project_app_configs(base_dir):
        top_level = cfg.name.split(".")[0]
        packages.add(top_level)

    # Fall back to ROOT_URLCONF if no project apps found
    if not packages:
        urlconf = getattr(django_settings, "ROOT_URLCONF", "")
        if urlconf and "." in urlconf:
            packages.add(urlconf.split(".")[0])

    return sorted(packages)


def _get_project_app_configs(base_dir: Path) -> list:
    """
    Return AppConfig instances whose source is inside the project directory
    and NOT inside a ``site-packages`` directory (which indicates a
    pip-installed third-party package, even when the virtualenv lives
    inside the project tree).
    """
    from django.apps import apps as django_apps

    project_apps = []
    base_resolved = str(base_dir.resolve())
    for cfg in django_apps.get_app_configs():
        try:
            mod = cfg.module
            mod_file = getattr(mod, "__file__", None)
            if not mod_file:
                continue
            mod_str = str(Path(mod_file).resolve())
            if not mod_str.startswith(base_resolved):
                continue
            if "site-packages" in mod_str:
                continue
            project_apps.append(cfg)
        except Exception:
            continue
    return project_apps


def build_module_to_app_map(
    root_packages: list[str] | None = None,
    project_dir: Path | None = None,
) -> dict[str, str]:
    """
    Build a canonical {AppConfig.name: normalised_label} mapping, sorted
    longest-first for greedy prefix matching.

    This is the single source of truth for module name → app label used
    by both the analyzer and the DjDT panel.
    """
    from django.apps import apps as django_apps

    rps = root_packages or []
    prefix_map: dict[str, str] = {}

    for cfg in django_apps.get_app_configs():
        label = cfg.label
        for rp in rps:
            prefix = rp.replace(".", "_") + "_"
            if label.startswith(prefix):
                label = label[len(prefix):]
                break
        prefix_map[cfg.name] = label

    return dict(sorted(prefix_map.items(), key=lambda kv: len(kv[0]), reverse=True))


def module_to_app(module_name: str, app_map: dict[str, str]) -> str | None:
    """Map a single module name to its app label using longest-prefix match."""
    for pkg_name, label in app_map.items():
        if module_name == pkg_name or module_name.startswith(pkg_name + "."):
            return label
    return None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AppNode:
    name: str
    models: list[str] = field(default_factory=list)


@dataclass
class ModelEdge:
    source_model: str
    target_model: str
    label: str = ""


@dataclass
class AppEdge:
    source: str
    target: str
    types: set[str] = field(default_factory=set)   # 'import', 'fk'
    violation: bool = False
    model_edges: list[ModelEdge] = field(default_factory=list)

    @property
    def coupling_strength(self) -> str:
        if self.violation:
            return "violation"
        if "import" in self.types and "fk" in self.types:
            return "both"
        if "fk" in self.types:
            return "fk"
        return "import"


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class DependencyAnalyzer:
    def __init__(
        self,
        root_packages: list[str],
        included_apps: Optional[list[str]] = None,
        manage_py_dir: Optional[str] = None,
        violations: Optional[list[tuple[str, str]]] = None,
        read_importlinter: bool = True,
        valid_app_labels: Optional[set[str]] = None,
        disable_grimp_cache: bool = False,
        app_map: Optional[dict[str, str]] = None,
    ):
        self.root_packages = root_packages
        self.included_apps = included_apps
        self.manage_py_dir = Path(manage_py_dir) if manage_py_dir else Path.cwd()
        self.violations = set(violations or [])
        self.read_importlinter = read_importlinter
        # If provided, grimp results are filtered to these app labels only
        # (prevents conftest.py, settings.py etc from appearing as apps)
        self.valid_app_labels = valid_app_labels
        # When True, passes cache_dir=None to grimp, bypassing the .grimp_cache
        # file cache. Used by the live view/refresh endpoint so changes to .py
        # files are always picked up without relying on mtime detection.
        self.disable_grimp_cache = disable_grimp_cache
        # Canonical module name → app label mapping (built from app registry).
        # When provided, replaces the old to_app() heuristic in import scanning.
        self.app_map = app_map
        self.app_nodes: dict[str, AppNode] = {}
        self.edges: dict[tuple[str, str], AppEdge] = {}
        # Apps found by grimp = user code; apps not found = FK-only (third-party)
        self._grimp_apps: set[str] = set()

    def analyze(self) -> dict:
        if self.read_importlinter:
            il_violations = _importlinter.load_violations(self.manage_py_dir)
            if il_violations:
                _warn(f"Loaded {len(il_violations)} violation pair(s) from .importlinter")
            self.violations.update(il_violations)

        self._analyze_models()
        self._analyze_imports()
        self._seed_project_apps()
        self._apply_violations()
        graph = self._serialize()

        import_cycles = find_cycles(graph["edges"], "import")
        fk_cycles     = find_cycles(graph["edges"], "fk")
        annotate_graph(graph, import_cycles + fk_cycles)
        return graph

    # ------------------------------------------------------------------
    # Model graph  (graph_models → DOT)
    # ------------------------------------------------------------------

    def _analyze_models(self):
        # --group-models is required to produce subgraph cluster_<app> blocks,
        # which is how we map node IDs back to their app label.
        cmd = [sys.executable, "manage.py", "graph_models", "--group-models"]
        if self.included_apps:
            cmd.extend(self.included_apps)
        else:
            cmd.append("-a")   # all applications

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=self.manage_py_dir,
            )
            if result.stdout.strip():
                self._parse_dot(result.stdout)
            else:
                _warn(
                    f"graph_models produced no output. "
                    f"stderr: {result.stderr[:300]}"
                )
        except FileNotFoundError:
            _warn("manage.py not found — run from your Django project root.")

    def _parse_dot(self, dot_content: str) -> None:
        """
        Parse the DOT produced by ``graph_models --group-models``.

        Node IDs are unquoted identifiers like ``billing_models_Invoice``.
        The model class name is embedded in the HTML label as ``<B>Invoice</B>``.
        Cross-app FK edges are written as two lines:

            billing_models_Invoice -> accounts_models_User
            [label=" customer (invoice)"] [arrowhead=none, arrowtail=dot, dir=both];

        The edge label has an optional `` (related_name)`` suffix we strip.
        """
        node_to_app:   dict[str, str] = {}   # node_id → app_label
        node_to_model: dict[str, str] = {}   # node_id → ModelName

        # First <B>...</B> after a node definition is the model class name
        # Uppercase-first = Django model class names; field names are lowercase so excluded
        _model_name_re   = re.compile(r"<B>\s*([A-Z]\w*)")
        # Unquoted node definitions inside a cluster: `  some_node_id [label`
        _node_def_re     = re.compile(r"^\s*(\w+)\s*\[label", re.MULTILINE)
        # Strip " (related_name)" suffix from edge labels
        _related_name_re = re.compile(r"\s*\([\w_]+\)\s*$")

        # ── Map every node to its app via cluster membership ──────────
        for raw_app_name, cluster_body in self._extract_clusters(dot_content).items():
            app_name = self._normalize_app_name(raw_app_name)
            if self.included_apps and app_name not in self.included_apps:
                continue

            app_node = self.app_nodes.setdefault(app_name, AppNode(name=app_name))

            for m in _node_def_re.finditer(cluster_body):
                node_id = m.group(1)
                label_m = _model_name_re.search(cluster_body, m.start())
                model_name = label_m.group(1) if label_m else node_id
                node_to_app[node_id]   = app_name
                node_to_model[node_id] = model_name
                if model_name not in app_node.models:
                    app_node.models.append(model_name)

        # ── Extract FK/M2M edges ──────────────────────────────────────
        # Two-line format:  nodeA -> nodeB\n  [label="..."]
        two_line = re.compile(
            r"(\w+)\s*->\s*(\w+)[\n\r]+\s*\[label=\"([^\"]*)\"",
            re.MULTILINE,
        )
        # One-line format:  nodeA -> nodeB [label="..."]
        one_line = re.compile(
            r"(\w+)\s*->\s*(\w+)\s*\[label=\"([^\"]*)\""
        )

        raw_edges: list[tuple[str, str, str]] = [
            (m.group(1), m.group(2), m.group(3))
            for m in two_line.finditer(dot_content)
        ]
        # Collect one-line edges not already covered by two-line matches
        two_line_pairs = {(s, t) for s, t, _ in raw_edges}
        for m in one_line.finditer(dot_content):
            pair = (m.group(1), m.group(2))
            if pair not in two_line_pairs:
                raw_edges.append((m.group(1), m.group(2), m.group(3)))

        for src_node, tgt_node, raw_label in raw_edges:
            src_app = node_to_app.get(src_node)
            tgt_app = node_to_app.get(tgt_node)

            if not src_app or not tgt_app or src_app == tgt_app:
                continue

            label     = _related_name_re.sub("", raw_label).strip()
            src_model = node_to_model.get(src_node, src_node)
            tgt_model = node_to_model.get(tgt_node, tgt_node)

            key  = (src_app, tgt_app)
            edge = self.edges.setdefault(key, AppEdge(source=src_app, target=tgt_app))
            edge.types.add("fk")
            edge.model_edges.append(ModelEdge(src_model, tgt_model, label))

    def _extract_clusters(self, dot_content: str) -> dict[str, str]:
        """Return {app_name: cluster_body_text} using brace counting."""
        result: dict[str, str] = {}
        pattern = re.compile(r"subgraph\s+cluster_(\w+)\s*\{")
        pos = 0
        while pos < len(dot_content):
            m = pattern.search(dot_content, pos)
            if not m:
                break
            app_name = m.group(1)
            start = m.end()
            depth, j = 1, start
            while j < len(dot_content) and depth > 0:
                if dot_content[j] == "{":
                    depth += 1
                elif dot_content[j] == "}":
                    depth -= 1
                j += 1
            result[app_name] = dot_content[start:j - 1]
            pos = j
        return result

    def _normalize_app_name(self, cluster_name: str) -> str:
        """
        Map a graph_models cluster name to the canonical app label.

        graph_models derives cluster names from ``AppConfig.name`` with dots
        replaced by underscores (e.g. ``django.contrib.auth`` →
        ``django_contrib_auth``).  This method maps those back to the
        canonical label used everywhere else (``auth``).

        Uses ``app_map`` when available for an exact lookup, then falls back
        to stripping root-package prefixes.
        """
        # Exact lookup via app_map: cluster_name is AppConfig.name with . → _
        if self.app_map:
            for cfg_name, label in self.app_map.items():
                if cfg_name.replace(".", "_") == cluster_name:
                    return label

        # Legacy fallback: strip root-package prefix
        for rp in self.root_packages:
            prefix = rp.replace(".", "_") + "_"
            if cluster_name.startswith(prefix):
                return cluster_name[len(prefix):]
        return cluster_name

    # ------------------------------------------------------------------
    # Import graph  (grimp)
    # ------------------------------------------------------------------

    def _analyze_imports(self):
        if not HAS_GRIMP:
            _warn("grimp not installed — import analysis skipped. pip install grimp")
            return

        if not self.root_packages:
            return

        # Pass ALL root packages to a single grimp.build_graph() call so that
        # cross-package imports are visible (e.g. dboard → test_project).
        # grimp only reports imports between packages it was asked to scan.
        try:
            grimp_kwargs = {"include_external_packages": False}
            if self.disable_grimp_cache:
                grimp_kwargs["cache_dir"] = None
            first, *rest = self.root_packages
            graph = grimp.build_graph(first, *rest, **grimp_kwargs)
            for root_package in self.root_packages:
                self._process_import_graph(graph, root_package)
        except Exception as exc:  # noqa: BLE001
            _warn(f"grimp failed for {self.root_packages!r}: {exc}")

    def _process_import_graph(self, graph, root_package: str):
        if self.app_map:
            # Use the canonical module→app mapping from the app registry.
            # This handles all layouts: top-level apps, nested apps, mixed.
            def to_app(mod: str) -> Optional[str]:
                return module_to_app(mod, self.app_map)
        else:
            # Legacy fallback: assume apps are subpackages of root_package.
            def to_app(mod: str) -> Optional[str]:
                parts = mod.split(".")
                return parts[1] if len(parts) >= 2 and parts[0] == root_package else None

        for mod in graph.modules:
            src_app = to_app(mod)
            if not src_app:
                continue
            if self.included_apps and src_app not in self.included_apps:
                continue
            if self.valid_app_labels and src_app not in self.valid_app_labels:
                continue

            for imported in graph.find_modules_directly_imported_by(mod):
                tgt_app = to_app(imported)
                if not tgt_app or tgt_app == src_app:
                    continue
                if self.included_apps and tgt_app not in self.included_apps:
                    continue
                if self.valid_app_labels and tgt_app not in self.valid_app_labels:
                    continue

                for app in (src_app, tgt_app):
                    self.app_nodes.setdefault(app, AppNode(name=app))
                    self._grimp_apps.add(app)

                key  = (src_app, tgt_app)
                edge = self.edges.setdefault(key, AppEdge(source=src_app, target=tgt_app))
                edge.types.add("import")

    # ------------------------------------------------------------------
    # Seed project apps (ensure isolated apps appear in the graph)
    # ------------------------------------------------------------------

    def _seed_project_apps(self):
        for label in _get_project_app_labels(self.manage_py_dir):
            self.app_nodes.setdefault(label, AppNode(name=label))

    # ------------------------------------------------------------------
    # Violations
    # ------------------------------------------------------------------

    def _apply_violations(self):
        for src, tgt in self.violations:
            key = (src, tgt)
            if key in self.edges:
                self.edges[key].violation = True

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _serialize(self) -> dict:
        in_degree:  dict[str, int] = {}
        out_degree: dict[str, int] = {}
        for (src, tgt) in self.edges:
            out_degree[src] = out_degree.get(src, 0) + 1
            in_degree[tgt]  = in_degree.get(tgt,  0) + 1

        project_labels = _get_project_app_labels(self.manage_py_dir)

        apps = {}
        for name, node in sorted(self.app_nodes.items()):
            apps[name] = {
                "name":          name,
                "models":        sorted(node.models),
                "model_count":   len(node.models),
                "in_degree":     in_degree.get(name, 0),
                "out_degree":    out_degree.get(name, 0),
                "is_third_party": name not in project_labels,
            }

        edges = []
        for edge in self.edges.values():
            edges.append({
                "source":      edge.source,
                "target":      edge.target,
                "types":       sorted(edge.types),
                "coupling":    edge.coupling_strength,
                "violation":   edge.violation,
                "model_edges": [
                    {"from": me.source_model, "to": me.target_model, "label": me.label}
                    for me in edge.model_edges
                ],
            })

        violations = [e for e in edges if e["violation"]]
        return {
            "apps":  apps,
            "edges": edges,
            "stats": {
                "app_count":          len(apps),
                "edge_count":         len(edges),
                "import_only_count":  sum(1 for e in edges if e["coupling"] == "import"),
                "fk_only_count":      sum(1 for e in edges if e["coupling"] == "fk"),
                "both_count":         sum(1 for e in edges if e["coupling"] == "both"),
                "violation_count":    len(violations),
                "has_grimp":          HAS_GRIMP,
            },
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_app_labels(project_dir: Path) -> set[str]:
    """
    Return the set of app labels whose source lives inside the project
    directory.  Apps in site-packages (Django contrib, third-party) are
    excluded.  This is the authoritative check for is_third_party.
    """
    labels: set[str] = set()
    for cfg in _get_project_app_configs(project_dir):
        labels.add(cfg.label)
    return labels


def _warn(msg: str):
    print(f"[dependency_map] WARNING: {msg}", file=sys.stderr)


class _fake_match:
    def group(self, _n): return ""
