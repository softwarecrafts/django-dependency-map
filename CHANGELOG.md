# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1]

### Fixed
- Plain Python packages now appear in the live debug view (`/__depmap__/`) as well as the management command output. Switched `_discover_plain_packages` from `importlib.import_module` to `importlib.util.find_spec` so discovery no longer executes the package's `__init__.py`; this avoids import-time exceptions (e.g. `AppRegistryNotReady`, circular imports) that silently suppressed discovery in a web-request context.
- Namespace packages (no `__init__.py`) are now supported as root packages via `spec.submodule_search_locations`.
- Broadened exception handling in plain-package discovery so a single broken root package can no longer null out the whole `app_map` via the outer `except Exception` in `_run_analysis`.

### Added
- Diagnostic warnings emitted once per process when a plain package can't be resolved (bad import, missing spec, or no source location) — helps future users diagnose configuration issues without log spam.

## [0.4.0] - 2026-04-17

### Added
- Support for plain Python packages in `DEPENDENCY_MAP_ROOT_PACKAGES`. Subpackages of a non-Django root package are auto-discovered and added as nodes alongside Django apps; flat packages become a single node. Django app internals (`migrations/`, `management/`, `templatetags/`, `locale/`) and subpackages of registered Django apps are excluded.

## [0.3.3] - 2026-04-13

### Fixed
- Regression in the display of third-party packages. Abstract-base-model nodes that appeared in foreign clusters are now skipped outright rather than reattributed, which was causing inherited FKs (e.g. `created_by`) to be incorrectly drawn between apps. Inheritance edges were already suppressed by edge classification.

## [0.3.2] - 2026-04-13

Duplicate release tag — points at the same commit as 0.3.1 (tagging mistake). No changes.

## [0.3.1] - 2026-04-13

### Fixed
- Abstract models causing spurious dependency cycles. `graph_models --group-models` duplicates abstract-base nodes into every cluster that inherits from them; the parser now detects foreign nodes via the node-ID prefix and resolves them to the true owning app instead of attributing FKs to each inheriting app.

## [0.3.0] - 2026-04-10

### Added
- Import-linter contract rule export. New "Rules" tab in the export panel generates ready-to-paste `.importlinter` contract rules from the currently visible graph.
- Root packages are now threaded through to the renderer and DjDT panel so exported rules reference the correct top-level package names.

### Changed
- Export panel redesigned from modal dialog to bottom-docked drawer for better visibility while inspecting the graph.

## [0.2.0] - 2026-04-09

### Added
- Model relationship classification: FK, O2O, M2M, and generic relations are now distinguished in the model-edge type, parsed from DOT arrow attributes via `_classify_dot_edge`.
- Per-edge `import_count` so edge thickness / tooltips can reflect import frequency.
- Cycle-break suggestions via `grimp.nominate_cycle_breakers()`. Suggested edges are surfaced both in the graph (`is_break_suggestion` flag) and as a structured list in the serialized output.
- Inheritance edges are now filtered out of the model graph — grimp already covers these via imports, so including them double-counts.

### Changed
- Edge parser rewritten to capture the full attribute string, enabling downstream edge classification.

## [0.1.0] - 2025-04-07

### Added
- `dependency_map` management command with `--open`, `--format`, `--output`, `--check` flags
- Model-level FK/M2M relationship extraction via `graph_models` (django-extensions)
- Import graph analysis via `grimp`
- Unified app-level graph merging both sources with coupling classification (`fk`, `import`, `both`)
- Interactive D3 v7 force-directed HTML visualisation (self-contained, no server required)
- Edge colour coding: FK (blue), import (green, dashed), both (purple), violation (red), cycle (orange)
- Node sizing proportional to model count
- Side panel: model list, instability metric, afferent/efferent coupling, dependency list
- Edge tooltip: model-level FK pairs and field names
- Filter buttons to toggle edge types independently
- `.importlinter` / `setup.cfg` contract auto-parsing (layers, independence, forbidden)
- Cycle detection via Tarjan's SCC algorithm
- Cycle visualisation: orange node halos, orange cycle edges, cycle panel section
- `--check` CI mode: structured stderr report, exits 1 on violations or cycles
- `--no-importlinter` flag to skip contract auto-loading
- `--violation SRC:TGT` flag for manual violation pairs
- `--root-package` flag (repeatable) for monorepo support
- JSON output mode (`--format json`)
