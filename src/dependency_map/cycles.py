"""
dependency_map.cycles
~~~~~~~~~~~~~~~~~~~~~
Finds cycles among Django apps using Tarjan's Strongly Connected Components.

Two independent passes are run:
  - import cycles  (circular Python imports)
  - fk cycles      (circular FK/M2M chains — valid in DB but risky for migrations)

Key distinction:

  SCC (Strongly Connected Component)
      A set of apps where every app can reach every other app via *some path*
      of edges. Apps are in the same SCC even if they have no direct edge —
      the connection may be transitive.  Do NOT use "→" between SCC members
      unless you have verified a direct edge exists.

  Direct cycle
      A pair (A, B) where BOTH A→B and B→A exist as direct edges.
      These are the most actionable: each pair is a concrete circular import
      that can be untangled without touching unrelated apps.

  Example path
      A shortest cycle path starting from the first app in the SCC,
      following only real edges.  This shows *one* concrete manifestation
      of the cycle, useful for understanding how the cycle actually works.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Cycle:
    apps: list[str]
    kind: str = "import"   # "import" | "fk"
    example_path: list[str] = field(default_factory=list)

    def label(self) -> str:
        """Human-readable summary that never implies non-existent direct edges."""
        if len(self.apps) == 2:
            return f"{self.apps[0]} ↔ {self.apps[1]}"
        return f"SCC of {len(self.apps)} apps: {', '.join(sorted(self.apps))}"

    def example_label(self) -> str:
        """One valid cycle path through real edges, or empty string."""
        if not self.example_path:
            return ""
        return " → ".join(self.example_path + [self.example_path[0]])

    # backwards compat — used in existing tests
    def __str__(self) -> str:
        return self.label()

    def contains(self, app: str) -> bool:
        return app in self.apps


def _tarjan_sccs(adjacency: dict[str, list[str]], all_nodes: set[str]) -> list[list[str]]:
    """Return non-trivial SCCs (size > 1) via Tarjan's algorithm."""
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def _strongconnect(v: str) -> None:
        index[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in adjacency.get(v, []):
            if w not in index:
                _strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1:
                sccs.append(scc)

    for node in sorted(all_nodes):
        if node not in index:
            _strongconnect(node)

    return sccs


def _bfs_shortest_cycle(start: str, adjacency: dict[str, list[str]], app_set: set[str]) -> list[str]:
    """
    BFS shortest cycle starting and ending at *start*, using only edges
    within *app_set*.  Returns the path WITHOUT the repeated start node,
    or an empty list if no cycle is found.
    """
    queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
    while queue:
        node, path = queue.popleft()
        if len(path) > len(app_set) + 1:   # safety limit
            break
        for nxt in sorted(adjacency.get(node, [])):
            if nxt not in app_set:
                continue
            if nxt == start and len(path) > 1:
                return path          # found cycle back to start
            if nxt not in path:
                queue.append((nxt, path + [nxt]))
    return []


def find_cycles(edges: list[dict], edge_type: str = "import") -> list[Cycle]:
    """
    Find all cycles of the given edge type using Tarjan's SCC algorithm.
    Also attaches a shortest example path to each Cycle for display purposes.

    ``edge_type`` is ``"import"`` (default) or ``"fk"``.
    """
    adjacency: dict[str, list[str]] = {}
    all_nodes: set[str] = set()

    for edge in edges:
        all_nodes.add(edge["source"])
        all_nodes.add(edge["target"])
        if edge_type in edge.get("types", []):
            adjacency.setdefault(edge["source"], []).append(edge["target"])

    cycles = []
    for scc in _tarjan_sccs(adjacency, all_nodes):
        app_set = set(scc)
        # Find a real shortest cycle starting from the first app alphabetically
        start = sorted(scc)[0]
        example = _bfs_shortest_cycle(start, adjacency, app_set)
        cycles.append(Cycle(apps=scc, kind=edge_type, example_path=example))

    return cycles


def find_direct_cycles(edges: list[dict], edge_type: str = "import") -> list[tuple[str, str]]:
    """
    Return sorted pairs (a, b) where both a→b and b→a exist for the given
    edge type.  These are the most actionable: a direct mutual dependency.
    """
    forward: set[tuple[str, str]] = set()
    for edge in edges:
        if edge_type in edge.get("types", []):
            forward.add((edge["source"], edge["target"]))

    return sorted(
        {(min(a, b), max(a, b)) for (a, b) in forward if (b, a) in forward},
        key=lambda p: p[0],
    )


def annotate_graph(graph: dict, cycles: list[Cycle]) -> dict:
    """
    Stamp cycle membership onto apps and edges in *graph*.

    Runs both import and FK cycle detection. Each app and edge gets:
      - ``in_import_cycle`` / ``import_cycle_index``
      - ``in_fk_cycle``     / ``fk_cycle_index``
      - ``in_cycle``        (True if in either)
      - ``cycle_index``     (first non-(-1) index, for backwards compat)
    """
    edges = graph["edges"]

    import_cycles = [c for c in cycles if c.kind == "import"]
    fk_cycles     = [c for c in cycles if c.kind == "fk"]

    if not any(c.kind == "import" for c in cycles):
        import_cycles = find_cycles(edges, "import")
    if not any(c.kind == "fk" for c in cycles):
        fk_cycles = find_cycles(edges, "fk")

    all_cycles = import_cycles + fk_cycles

    def _app_map(cycle_list: list[Cycle]) -> dict[str, int]:
        m: dict[str, int] = {}
        for i, c in enumerate(cycle_list):
            for app in c.apps:
                m.setdefault(app, i)
        return m

    import_app_map = _app_map(import_cycles)
    fk_app_map     = _app_map(fk_cycles)

    for app_name, app_data in graph["apps"].items():
        imp_idx = import_app_map.get(app_name, -1)
        fk_idx  = fk_app_map.get(app_name, -1)
        app_data["in_import_cycle"]    = imp_idx >= 0
        app_data["import_cycle_index"] = imp_idx
        app_data["in_fk_cycle"]        = fk_idx >= 0
        app_data["fk_cycle_index"]     = fk_idx
        app_data["in_cycle"]           = imp_idx >= 0 or fk_idx >= 0
        app_data["cycle_index"]        = imp_idx if imp_idx >= 0 else fk_idx

    def _same_cycle(src: str, tgt: str, app_map: dict[str, int]) -> bool:
        s, t = app_map.get(src, -1), app_map.get(tgt, -1)
        return s >= 0 and s == t

    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        types = edge.get("types", [])
        imp_cycle = _same_cycle(src, tgt, import_app_map) and "import" in types
        fk_cycle  = _same_cycle(src, tgt, fk_app_map)     and "fk"     in types
        edge["in_import_cycle"]   = imp_cycle
        edge["in_fk_cycle"]       = fk_cycle
        edge["in_cycle"]          = imp_cycle or fk_cycle
        edge["cycle_index"]       = (
            import_app_map.get(src, -1) if imp_cycle
            else fk_app_map.get(src, -1) if fk_cycle
            else -1
        )

    graph["cycles"] = [
        {
            "apps":         c.apps,
            "label":        c.label(),        # never uses → for non-existent edges
            "example_path": c.example_label(),# one real valid path, clearly labelled
            "kind":         c.kind,
        }
        for c in all_cycles
    ]

    graph["direct_import_cycles"] = [
        {"a": a, "b": b, "label": f"{a} ↔ {b}"}
        for a, b in find_direct_cycles(edges, "import")
    ]
    graph["direct_fk_cycles"] = [
        {"a": a, "b": b, "label": f"{a} ↔ {b}"}
        for a, b in find_direct_cycles(edges, "fk")
    ]
    graph["stats"]["cycle_count"]               = len(all_cycles)
    graph["stats"]["import_cycle_count"]        = len(import_cycles)
    graph["stats"]["fk_cycle_count"]            = len(fk_cycles)
    graph["stats"]["direct_import_cycle_count"] = len(graph["direct_import_cycles"])
    graph["stats"]["direct_fk_cycle_count"]     = len(graph["direct_fk_cycles"])
    graph["stats"]["cyclic_app_count"]          = len(
        {app for c in all_cycles for app in c.apps}
    )

    return graph
