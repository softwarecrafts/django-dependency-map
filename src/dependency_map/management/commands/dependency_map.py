"""
management/commands/dependency_map.py
"""
from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Generate an interactive dependency map merging model FKs and import relationships."

    def add_arguments(self, parser):
        parser.add_argument("apps", nargs="*")
        parser.add_argument("--root-package", dest="root_packages", action="append", default=[], metavar="PKG")
        parser.add_argument("--no-importlinter", dest="no_importlinter", action="store_true")
        parser.add_argument("--violation", dest="violations", action="append", default=[], metavar="SRC:TGT")
        parser.add_argument("--check", action="store_true", dest="check_mode")
        parser.add_argument("--output", default=None, metavar="PATH")
        parser.add_argument("--format", choices=["html", "json"], default="html")
        parser.add_argument("--open", action="store_true", dest="open_browser")
        parser.add_argument("--title", default=None)

    def handle(self, *args, **options):
        from dependency_map.analyzer import (
            DependencyAnalyzer,
            build_module_to_app_map,
            discover_root_packages,
        )
        from dependency_map.renderer import write_html

        root_packages = options["root_packages"] or discover_root_packages()
        if not root_packages:
            raise CommandError("Could not determine root package. Pass --root-package <myproject>.")
        self.stdout.write(f"Root packages: {', '.join(root_packages)}")

        manual_violations = []
        for v in options["violations"]:
            if ":" not in v:
                raise CommandError(f"Invalid violation format '{v}' — expected 'src:tgt'.")
            src, tgt = v.split(":", 1)
            manual_violations.append((src.strip(), tgt.strip()))

        self.stdout.write("Analyzing model relationships via graph_models…")
        self.stdout.write("Analyzing import graph via grimp…")

        try:
            app_map = build_module_to_app_map(root_packages)
            valid_app_labels = set(app_map.values())
        except Exception:
            app_map = None
            valid_app_labels = None

        analyzer = DependencyAnalyzer(
            root_packages=root_packages,
            included_apps=options["apps"] or None,
            violations=manual_violations,
            read_importlinter=not options["no_importlinter"],
            valid_app_labels=valid_app_labels,
            app_map=app_map,
        )
        graph = analyzer.analyze()
        stats = graph["stats"]

        self.stdout.write(self.style.SUCCESS(
            f"Found {stats['app_count']} apps, {stats['edge_count']} edges "
            f"({stats['fk_only_count']} FK-only, {stats['import_only_count']} import-only, "
            f"{stats['both_count']} both, {stats['violation_count']} violations, "
            f"{stats.get('cycle_count', 0)} cycles)"
        ))
        if not stats["has_grimp"]:
            self.stdout.write(self.style.WARNING("  grimp not installed — import edges omitted. pip install grimp"))

        if options["check_mode"]:
            return self._run_check(graph)

        fmt = options["format"]
        if fmt == "json":
            output = options["output"] or "dependency_map.json"
            Path(output).write_text(json.dumps(graph, indent=2))
            self.stdout.write(self.style.SUCCESS(f"JSON written to: {output}"))
            return

        output = options["output"] or "dependency_map.html"
        title = options["title"] or self._guess_title()
        write_html(graph, output, title=title)
        self.stdout.write(self.style.SUCCESS(f"HTML written to: {output}"))

        if options["open_browser"]:
            webbrowser.open(f"file://{Path(output).resolve()}")

    def _run_check(self, graph: dict) -> None:
        violations = [e for e in graph["edges"] if e["violation"]]
        cycles = graph.get("cycles", [])
        has_issues = bool(violations or cycles)

        if violations:
            self.stderr.write(self.style.ERROR(f"\n✗ {len(violations)} import violation(s) found:\n"))
            for edge in violations:
                self.stderr.write(self.style.ERROR(f"  {edge['source']} → {edge['target']}  [{' + '.join(edge['types'])}]"))
                for me in edge.get("model_edges", []):
                    label = f" ({me['label']})" if me.get("label") else ""
                    self.stderr.write(f"    FK: {me['from']} → {me['to']}{label}")
        else:
            self.stdout.write(self.style.SUCCESS("✓ No import violations"))

        direct_imp = graph.get("direct_import_cycles", [])
        direct_fk  = graph.get("direct_fk_cycles", [])

        if direct_imp:
            self.stderr.write(self.style.ERROR(f"\n✗ {len(direct_imp)} direct mutual import(s) — fix these first:\n"))
            for d in direct_imp:
                self.stderr.write(self.style.ERROR(f"  {d['a']} ↔ {d['b']}"))
        if cycles:
            import_sccs = [c for c in cycles if c["kind"] == "import"]
            if import_sccs:
                self.stderr.write(self.style.ERROR(f"\n✗ {len(import_sccs)} import cycle group(s):\n"))
                for c in import_sccs:
                    app_list = ', '.join(sorted(c['apps']))
                    self.stderr.write(self.style.ERROR(f"  {c['label']}"))
                    if c.get('example_path'):
                        self.stderr.write(f"    e.g. {c['example_path']}")
        if direct_fk:
            self.stderr.write(self.style.ERROR(f"\n✗ {len(direct_fk)} direct mutual FK(s) — migration ordering risk:\n"))
            for d in direct_fk:
                self.stderr.write(self.style.ERROR(f"  {d['a']} ↔ {d['b']}"))
        if not direct_imp and not cycles:
            self.stdout.write(self.style.SUCCESS("✓ No import cycles"))
        if not direct_fk and not [c for c in cycles if c["kind"] == "fk"]:
            self.stdout.write(self.style.SUCCESS("✓ No FK cycles"))

        if has_issues:
            self.stderr.write("")
            raise SystemExit(1)

    def _guess_title(self) -> str:
        from django.conf import settings
        urlconf = getattr(settings, "ROOT_URLCONF", "")
        return f"{urlconf.split('.')[0]} — Dependency Map" if urlconf else "Django Dependency Map"
