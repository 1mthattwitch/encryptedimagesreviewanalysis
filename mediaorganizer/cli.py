"""
Command-line interface for mediaorganizer.

Usage:
  python -m mediaorganizer PATH [options]

  --recursive / --no-recursive  (default: recursive)
  --check-health                run health checks
  --find-duplicates             find exact + near duplicates
  --analyze                     AI describe + categorize (requires Ollama)
  --no-ai                       use heuristics only (skip Ollama)
  --storage-report              print storage breakdown
  --mode {type,date,content,event}
  --apply                       execute moves (default: dry-run)
  --output DIR                  where to move files (default: ./Organized)
  --export-json FILE
  --export-csv FILE
  --export-html DIR
  --export-map FILE             GPS HTML map
  --quality                     score photo quality
  --faces                       detect + count faces
  --ocr                         extract text from images (Tesseract)
  --fix-rotation                apply EXIF orientation physically
  --strip-gps                   remove GPS tags
  --heic-convert                convert HEIC→JPG
  --fix-timestamps              sync file mtime to EXIF date
  --ollama-host URL             (default: http://localhost:11434)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mediaorganizer",
        description="Offline media scanner, AI renamer, and organiser",
    )
    parser.add_argument("path", type=Path, help="Folder to scan")
    parser.add_argument("-r", "--recursive", action="store_true", default=True)
    parser.add_argument("--no-recursive", dest="recursive", action="store_false")
    parser.add_argument("--check-health", action="store_true")
    parser.add_argument("--find-duplicates", action="store_true")
    parser.add_argument("--analyze", action="store_true",
                        help="AI describe and categorize (Ollama)")
    parser.add_argument("--no-ai", action="store_true",
                        help="Use heuristics only, skip Ollama")
    parser.add_argument("--storage-report", action="store_true")
    parser.add_argument("--mode", choices=["type", "date", "content", "event"],
                        default="type")
    parser.add_argument("--apply", action="store_true",
                        help="Execute moves (default: dry-run)")
    parser.add_argument("--output", type=Path, default=Path("./Organized"))
    parser.add_argument("--export-json", type=Path)
    parser.add_argument("--export-csv", type=Path)
    parser.add_argument("--export-html", type=Path)
    parser.add_argument("--export-map", type=Path)
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--faces", action="store_true")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--fix-rotation", action="store_true")
    parser.add_argument("--strip-gps", action="store_true")
    parser.add_argument("--heic-convert", action="store_true")
    parser.add_argument("--fix-timestamps", action="store_true")
    parser.add_argument("--ollama-host", default="http://localhost:11434")

    args = parser.parse_args(argv)
    folder = args.path.resolve()

    if not folder.is_dir():
        print(f"Error: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    from . import scanner, health, duplicates, analyzer, organizer, reporter, exporter

    print(f"Scanning {folder} …")
    entries = scanner.scan(folder, recursive=args.recursive)
    print(f"Found {len(entries)} files")

    if args.check_health:
        print("Running health checks …")
        health.check_all(entries)

    if args.heic_convert:
        from . import converter
        print("Converting HEIC → JPG …")
        converted = converter.batch_convert_heic(folder)
        print(f"  Converted {len(converted)} files")
        # Re-scan to include new JPGs
        entries = scanner.scan(folder, recursive=args.recursive)

    if args.fix_rotation:
        from . import converter
        print("Fixing EXIF rotation …")
        count = 0
        for e in entries:
            if e.file_type == "image" and e.mime_ext in ("jpg", "jpeg"):
                try:
                    converter.fix_rotation(e.path)
                    count += 1
                except Exception:
                    pass
        print(f"  Fixed rotation on {count} images")

    if args.strip_gps:
        from . import converter
        print("Stripping GPS metadata …")
        count = 0
        for e in entries:
            if e.file_type == "image":
                try:
                    converter.strip_metadata(e.path, strip_gps_only=True)
                    count += 1
                except Exception:
                    pass
        print(f"  Stripped GPS from {count} images")

    if args.quality:
        from . import quality
        print("Scoring image quality …")
        quality.score_all(entries)
        graded = {g: sum(1 for e in entries if e.quality_grade == g)
                  for g in ("A", "B", "C", "D", "F")}
        for g, n in graded.items():
            if n:
                print(f"  Grade {g}: {n}")

    if args.faces:
        from . import faces
        print("Detecting faces …")
        for e in entries:
            faces.update_entry_face_count(e)
        total_faces = sum(e.face_count or 0 for e in entries)
        print(f"  Detected {total_faces} faces across {len(entries)} files")

    if args.ocr:
        from . import ocr
        if ocr.is_available():
            print("Running OCR …")
            ocr.extract_all(entries)
        else:
            print("OCR skipped: Tesseract not found. "
                  "Install from https://tesseract-ocr.github.io/")

    if args.analyze:
        use_ai = not args.no_ai
        print(f"Analyzing files (AI={'Ollama' if use_ai else 'heuristics'}) …")
        def _cb(i, t): print(f"  {i}/{t}", end="\r")
        analyzer.analyze_all(entries, host=args.ollama_host,
                              use_ai=use_ai, progress_cb=_cb)
        print()

    if args.find_duplicates:
        print("Finding duplicates …")
        groups = duplicates.find_duplicates(entries)
        dr = reporter.duplicate_report(groups)
        print(f"  Groups: {dr['total_groups']} ({dr['exact_groups']} exact, "
              f"{dr['near_groups']} near)")
        print(f"  Recoverable space: {dr['wasted_human']}")
    else:
        groups = []

    if args.storage_report:
        reporter.print_report(entries, groups if args.find_duplicates else None)

    if args.fix_timestamps:
        from . import repair
        n = repair.fix_all_timestamps(entries)
        print(f"Fixed timestamps on {n} files")

    # Organise
    if args.mode or args.apply:
        log_path = args.output / "move_log.json"
        moves = organizer.plan_moves(entries, args.output, mode=args.mode)
        print(f"\nOrganise plan ({args.mode} mode): {len(moves)} moves")
        if not args.apply:
            print("  (dry-run — pass --apply to execute)")
            for entry, dest in moves[:20]:
                print(f"  {entry.path.name} → {dest.relative_to(args.output)}")
            if len(moves) > 20:
                print(f"  … and {len(moves) - 20} more")
        else:
            print("  Executing …")
            records = organizer.apply_moves(moves, log_path=log_path)
            ok = sum(1 for r in records if r["ok"])
            fail = len(records) - ok
            print(f"  Moved {ok} files" + (f", {fail} failed" if fail else ""))

    # Exports
    if args.export_json:
        exporter.export_json(entries, args.export_json)
        print(f"JSON manifest → {args.export_json}")
    if args.export_csv:
        exporter.export_csv(entries, args.export_csv)
        print(f"CSV → {args.export_csv}")
    if args.export_html:
        out = exporter.export_html(entries, args.export_html)
        print(f"HTML gallery → {out}")
    if args.export_map:
        from . import mapview
        mapview.export_map(entries, args.export_map)
        print(f"GPS map → {args.export_map}")

    print("\nDone.")


if __name__ == "__main__":
    main()
