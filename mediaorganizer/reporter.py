"""Storage and health report generation."""
from __future__ import annotations

from pathlib import Path

from .scanner import FileEntry


def generate(entries: list[FileEntry], duplicate_groups: dict) -> dict:
    total_size = sum(e.size_bytes for e in entries)

    by_type: dict[str, dict] = {}
    for e in entries:
        t = e.file_type
        if t not in by_type:
            by_type[t] = {'count': 0, 'size': 0}
        by_type[t]['count'] += 1
        by_type[t]['size'] += e.size_bytes

    unhealthy = [e for e in entries if not e.health_ok]
    duplicates = [e for e in entries if e.is_duplicate]

    recoverable = 0
    for group in duplicate_groups.values():
        sorted_group = sorted(group, key=lambda e: e.size_bytes)
        recoverable += sum(e.size_bytes for e in sorted_group[1:])

    largest = sorted(entries, key=lambda e: e.size_bytes, reverse=True)[:10]

    return {
        'total_files': len(entries),
        'total_size_bytes': total_size,
        'by_type': by_type,
        'unhealthy_count': len(unhealthy),
        'unhealthy_files': [str(e.path) for e in unhealthy],
        'duplicate_count': len(duplicates),
        'duplicate_groups': len(duplicate_groups),
        'recoverable_bytes': recoverable,
        'largest_files': [{'path': str(e.path), 'size': e.size_bytes} for e in largest],
    }


def _human(b: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if b < 1024:
            return f'{b:.1f} {unit}'
        b /= 1024
    return f'{b:.1f} PB'


def format_report(report: dict) -> str:
    sep = '=' * 52
    lines = [
        sep,
        '  MEDIA ORGANIZER  --  STORAGE REPORT',
        sep,
        f"  Total files   : {report['total_files']:,}",
        f"  Total size    : {_human(report['total_size_bytes'])}",
        '',
        '  By type:',
    ]

    max_size = max((v['size'] for v in report['by_type'].values()), default=1)
    for t, info in sorted(report['by_type'].items(), key=lambda x: -x[1]['size']):
        pct = info['size'] / max(report['total_size_bytes'], 1) * 100
        filled = int(info['size'] / max_size * 20)
        bar = ('█' * filled).ljust(20, '░')
        lines.append(f"    {t:<12} {info['count']:>5} files  {_human(info['size']):>10}  {bar} {pct:.0f}%")

    lines += [
        '',
        f"  Unhealthy files   : {report['unhealthy_count']}",
        f"  Duplicate groups  : {report['duplicate_groups']} ({report['duplicate_count']} files)",
        f"  Recoverable space : {_human(report['recoverable_bytes'])}",
        '',
        '  Top 10 largest files:',
    ]
    for item in report['largest_files']:
        p = Path(item['path'])
        lines.append(f"    {_human(item['size']):>10}  {p.name}")

    if report['unhealthy_files']:
        lines += ['', '  Unhealthy files:']
        for f in report['unhealthy_files'][:20]:
            lines.append(f'    {f}')

    lines.append(sep)
    return '\n'.join(lines)
