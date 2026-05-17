"""Command-line entry point for mediaorganizer."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import scanner, health, duplicates, analyzer, organizer, reporter, exporter


def main() -> None:
    p = argparse.ArgumentParser(
        prog='mediaorganizer',
        description='Offline media organizer — scan, analyze, rename, and organize your files.',
    )
    p.add_argument('path', nargs='?', default='.', help='Directory to scan (default: current dir)')
    p.add_argument('-r', '--recursive', action='store_true', default=True)
    p.add_argument('--apply', action='store_true', help='Actually move files (default: dry-run)')
    p.add_argument('--mode', choices=['type', 'date', 'content'], default='type',
                   help='Organization mode (default: type)')
    p.add_argument('--output', default='./Organized', metavar='DIR')
    p.add_argument('--check-health', action='store_true')
    p.add_argument('--find-duplicates', action='store_true')
    p.add_argument('--storage-report', action='store_true')
    p.add_argument('--analyze', action='store_true', help='Run Ollama analysis')
    p.add_argument('--export-manifest', metavar='FILE.json')
    p.add_argument('--export-csv', metavar='FILE.csv')
    p.add_argument('--export-gallery', metavar='DIR')
    p.add_argument('--ollama-host', default='http://localhost:11434')
    args = p.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f'Error: {root} is not a directory', file=sys.stderr)
        sys.exit(1)

    print(f'Scanning {root} ...')
    entries = scanner.scan(root, recursive=args.recursive)
    print(f'Found {len(entries)} files.')

    if args.check_health:
        print('Checking health...')
        for e in entries:
            result = health.check(e)
            e.health_ok = result.ok
            e.health_issues = result.issues
        bad = sum(1 for e in entries if not e.health_ok)
        print(f'  {bad} unhealthy files found.')

    dup_groups: dict = {}
    if args.find_duplicates:
        print('Finding duplicates...')
        dup_groups = duplicates.find_duplicates(entries)
        print(f'  Found {len(dup_groups)} duplicate groups.')

    ai = analyzer.OllamaAnalyzer(host=args.ollama_host)
    if args.analyze or args.mode == 'content':
        if not ai.is_available():
            print('Warning: Ollama not available — using heuristic names.')
        else:
            print('Analyzing with Ollama...')

        def _prog(i: int, total: int, name: str) -> None:
            print(f'  [{i + 1}/{total}] {name}', end='\r')

        analyzer.analyze_entries(entries, ai,
                                 need_category=(args.mode == 'content'),
                                 progress_cb=_prog)
        print()

    report = reporter.generate(entries, dup_groups)

    if args.storage_report:
        print(reporter.format_report(report))

    if args.export_manifest:
        out = Path(args.export_manifest)
        exporter.export_json(entries, report, out)
        print(f'Manifest: {out}')
    if args.export_csv:
        out = Path(args.export_csv)
        exporter.export_csv(entries, out)
        print(f'CSV: {out}')
    if args.export_gallery:
        out = Path(args.export_gallery)
        exporter.export_html(entries, report, out)
        print(f'Gallery: {out / "index.html"}')

    out_dir = Path(args.output).resolve()
    moves = organizer.plan_moves(entries, out_dir, args.mode)
    if args.apply:
        print(f'Moving {len(moves)} files to {out_dir} ...')
        results = organizer.apply_moves(moves, dry_run=False)
        ok = sum(1 for _, _, success, _ in results if success)
        print(f'Done: {ok}/{len(moves)} files moved.')
    else:
        print(f'\nDry-run — {len(moves)} proposed moves (pass --apply to execute):')
        for entry, dest in moves[:25]:
            try:
                rel = dest.relative_to(out_dir.parent)
            except ValueError:
                rel = dest
            print(f'  {entry.path.name:<40}  ->  {rel}')
        if len(moves) > 25:
            print(f'  ... and {len(moves) - 25} more')


if __name__ == '__main__':
    main()
