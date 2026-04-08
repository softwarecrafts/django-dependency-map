"""
dependency_map.importlinter
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reads ``.importlinter`` (or ``setup.cfg`` / ``pyproject.toml``) and converts
contract definitions into (source_app, target_app) violation pairs that the
analyzer can apply to edges.

Supported contract types
------------------------
layers
    Top layers may import bottom layers, never the reverse.
    Violations = any upward import detected in the graph.

independence
    Listed modules must not import each other at all.
    Violations = any edge between any two listed apps.

forbidden
    source_modules must not import forbidden_modules.
    Violations = any edge from a source app to a forbidden app.
"""
from __future__ import annotations

import configparser
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_violations(
    project_root: Optional[str | Path] = None,
) -> list[tuple[str, str]]:
    """
    Parse the importlinter config and return all *potential* violation pairs:
    (source_app, target_app).

    Only pairs that actually exist as edges in the graph will end up marked
    as violations — that filtering happens in ``DependencyAnalyzer``.
    """
    root = Path(project_root) if project_root else Path.cwd()
    config = _find_and_parse(root)
    if config is None:
        return []

    violations: list[tuple[str, str]] = []
    contracts = _extract_contracts(config)

    for contract in contracts:
        ctype = contract.get("type", "").strip().lower()
        if ctype == "layers":
            violations.extend(_layers_violations(contract))
        elif ctype == "independence":
            violations.extend(_independence_violations(contract))
        elif ctype == "forbidden":
            violations.extend(_forbidden_violations(contract))
        else:
            _warn(f"Unknown contract type '{ctype}' — skipping.")

    # Deduplicate
    return list(dict.fromkeys(violations))


def describe_contracts(project_root: Optional[str | Path] = None) -> list[dict]:
    """Return a human-readable list of contracts for display in --check output."""
    root = Path(project_root) if project_root else Path.cwd()
    config = _find_and_parse(root)
    if config is None:
        return []
    return _extract_contracts(config)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _find_and_parse(root: Path) -> Optional[configparser.ConfigParser]:
    """Try .importlinter, then setup.cfg, then pyproject.toml."""
    for candidate in [".importlinter", "setup.cfg"]:
        path = root / candidate
        if path.exists():
            cfg = configparser.ConfigParser()
            cfg.read(str(path))
            if any(s.startswith("importlinter") for s in cfg.sections()):
                return cfg

    # pyproject.toml — look for [tool.importlinter] sections
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        return _parse_pyproject(pyproject)

    return None


def _parse_pyproject(path: Path) -> Optional[configparser.ConfigParser]:
    """
    Very light toml → configparser shim.  We only need importlinter sections.
    Avoids requiring a toml library (Python < 3.11 compat).
    """
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            _warn("tomllib/tomli not available — cannot parse pyproject.toml")
            return None

    with open(path, "rb") as f:
        data = tomllib.load(f)

    tool = data.get("tool", {})
    il = tool.get("importlinter", {})
    if not il:
        return None

    # Synthesise a configparser object
    cfg = configparser.ConfigParser()
    cfg["importlinter"] = {k: str(v) for k, v in il.items() if not isinstance(v, dict)}

    for contract_name, contract_data in il.items():
        if isinstance(contract_data, dict):
            section = f"importlinter:contract:{contract_name}"
            cfg[section] = {k: "\n    ".join(v) if isinstance(v, list) else str(v)
                            for k, v in contract_data.items()}
    return cfg


# ---------------------------------------------------------------------------
# Contract extraction
# ---------------------------------------------------------------------------


def _extract_contracts(cfg: configparser.ConfigParser) -> list[dict]:
    contracts = []
    for section in cfg.sections():
        if re.match(r"importlinter:contract:", section):
            contracts.append(dict(cfg[section]))
    return contracts


def _multiline_value(raw: str) -> list[str]:
    """Split a multi-line importlinter value into a clean list of strings."""
    return [
        line.strip()
        for line in raw.strip().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _pkg_to_app(module_path: str) -> str:
    """
    Convert a dotted module path to an app name.

    'myproject.billing'       → 'billing'
    'myproject.billing.views' → 'billing'
    'billing'                 → 'billing'
    """
    parts = module_path.strip().split(".")
    # If at least 2 parts, skip the root package (first segment)
    return parts[1] if len(parts) >= 2 else parts[0]


# ---------------------------------------------------------------------------
# Contract type handlers
# ---------------------------------------------------------------------------


def _layers_violations(contract: dict) -> list[tuple[str, str]]:
    """
    Layers are listed top-to-bottom.  Higher layers may import lower ones.
    Any import from a lower layer to a higher layer is a violation.

    layers =
        billing
        |users
        core

    Pipes (|) separate containers within the same level — treat as same layer.
    """
    raw = contract.get("layers", "")
    layer_strs = _multiline_value(raw)

    # Each line may contain pipe-separated peers at the same layer level
    layers: list[list[str]] = []
    for line in layer_strs:
        peers = [_pkg_to_app(p.strip()) for p in line.split("|") if p.strip()]
        if peers:
            layers.append(peers)

    violations: list[tuple[str, str]] = []
    # layer[i] can import layer[j] where j > i (lower in the stack)
    # any edge layer[j] → layer[i] (upward) is a violation
    for i, upper_peers in enumerate(layers):
        for j, lower_peers in enumerate(layers):
            if j <= i:
                continue  # same level or above — skip
            for lower_app in lower_peers:
                for upper_app in upper_peers:
                    # lower_app importing upper_app = upward violation
                    violations.append((lower_app, upper_app))

    return violations


def _independence_violations(contract: dict) -> list[tuple[str, str]]:
    """Any import between any two listed modules is a violation."""
    raw = contract.get("modules", "")
    apps = [_pkg_to_app(m) for m in _multiline_value(raw)]

    violations: list[tuple[str, str]] = []
    for i, src in enumerate(apps):
        for j, tgt in enumerate(apps):
            if i != j:
                violations.append((src, tgt))
    return violations


def _forbidden_violations(contract: dict) -> list[tuple[str, str]]:
    """source_modules must not import forbidden_modules."""
    sources  = [_pkg_to_app(m) for m in _multiline_value(contract.get("source_modules", ""))]
    forbidden = [_pkg_to_app(m) for m in _multiline_value(contract.get("forbidden_modules", ""))]

    return [(src, tgt) for src in sources for tgt in forbidden]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _warn(msg: str):
    print(f"[dependency_map:importlinter] WARNING: {msg}", file=sys.stderr)
