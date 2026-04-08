# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
