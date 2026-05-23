"""
Storage reports: size breakdown, top-N largest, duplicate savings, health summary.
"""

from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry
    from .duplicates import DuplicateGroup


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def storage_report(entries: list["FileEntry"]) -> dict:
    total_bytes = sum(e.size_bytes for e in entries)
    by_type: dict[str, int] = defaultdict(int)
    by_type_count: dict[str, int] = defaultdict(int)
    for e in entries:
        by_type[e.file_type] += e.size_bytes
        by_type_count[e.file_type] += 1

    top10 = sorted(entries, key=lambda e: e.size_bytes, reverse=True)[:10]

    return {
        "total_files": len(entries),
        "total_bytes": total_bytes,
        "total_human": _human(total_bytes),
        "by_type": {
            t: {"bytes": b, "human": _human(b), "count": by_type_count[t]}
            for t, b in sorted(by_type.items(), key=lambda x: -x[1])
        },
        "top10_largest": [
            {"path": str(e.path), "size": e.size_bytes, "human": _human(e.size_bytes)}
            for e in top10
        ],
    }


def duplicate_report(groups: list["DuplicateGroup"]) -> dict:
    wasted = sum(g.wasted_bytes for g in groups)
    return {
        "total_groups": len(groups),
        "exact_groups": sum(1 for g in groups if g.kind == "exact"),
        "near_groups": sum(1 for g in groups if g.kind == "near"),
        "wasted_bytes": wasted,
        "wasted_human": _human(wasted),
    }


def health_report(entries: list["FileEntry"]) -> dict:
    ok = [e for e in entries if e.health_ok]
    bad = [e for e in entries if not e.health_ok]
    return {
        "healthy": len(ok),
        "unhealthy": len(bad),
        "issues": [
            {"path": str(e.path), "issues": e.health_issues}
            for e in bad
        ],
    }


def print_report(
    entries: list["FileEntry"],
    groups: list["DuplicateGroup"] | None = None,
) -> None:
    sr = storage_report(entries)
    hr = health_report(entries)

    print(f"\n{'='*60}")
    print(f"  MEDIA ORGANIZER — SCAN REPORT")
    print(f"{'='*60}")
    print(f"  Total files : {sr['total_files']:,}")
    print(f"  Total size  : {sr['total_human']}")
    print(f"\n  By type:")
    for t, info in sr["by_type"].items():
        bar = "█" * min(int(info["bytes"] / max(sr["total_bytes"], 1) * 30), 30)
        print(f"    {t:<12} {bar:<30} {info['human']:>8}  ({info['count']} files)")

    print(f"\n  Top 10 largest files:")
    for item in sr["top10_largest"]:
        print(f"    {item['human']:>8}  {item['path']}")

    print(f"\n  Health:")
    print(f"    Healthy   : {hr['healthy']}")
    print(f"    Unhealthy : {hr['unhealthy']}")
    for issue in hr["issues"][:5]:
        print(f"    ⚠  {issue['path']}: {', '.join(issue['issues'])}")
    if len(hr["issues"]) > 5:
        print(f"    … and {len(hr['issues']) - 5} more")

    if groups is not None:
        dr = duplicate_report(groups)
        print(f"\n  Duplicates:")
        print(f"    Groups     : {dr['total_groups']} ({dr['exact_groups']} exact, {dr['near_groups']} near)")
        print(f"    Recoverable: {dr['wasted_human']}")

    print(f"{'='*60}\n")
