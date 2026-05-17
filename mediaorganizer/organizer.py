"""Plan and execute file moves into organised folder structures."""
from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path
from typing import Callable, Optional

from .scanner import FileEntry

TYPE_FOLDERS = {
    'image': 'Images',
    'video': 'Videos',
    'pdf': 'PDFs',
    'document': 'Documents',
    'unknown': 'Other',
}


def _unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while True:
        candidate = dest.parent / f'{stem}_{i}{suffix}'
        if not candidate.exists():
            return candidate
        i += 1


def _safe_name(name: str, max_len: int = 100) -> str:
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:max_len] or 'unnamed'


def _dest_dir(entry: FileEntry, output_dir: Path, mode: str) -> Path:
    if not entry.health_ok:
        return output_dir / 'Unreadable'
    if entry.is_duplicate:
        return output_dir / 'Duplicates'

    type_folder = TYPE_FOLDERS.get(entry.file_type, 'Other')

    if mode == 'type':
        return output_dir / type_folder

    if mode == 'date':
        if entry.date:
            return output_dir / type_folder / str(entry.date.year) / f'{entry.date.month:02d}'
        return output_dir / type_folder / 'Unknown_Date'

    if mode == 'content':
        cat = entry.ai_category or 'Other'
        return output_dir / cat

    return output_dir / type_folder


def plan_moves(
    entries: list[FileEntry],
    output_dir: Path,
    mode: str,
) -> list[tuple[FileEntry, Path]]:
    """Return (entry, destination_path) pairs without touching the filesystem."""
    moves: list[tuple[FileEntry, Path]] = []
    _seen: set[Path] = set()

    for entry in entries:
        folder = _dest_dir(entry, output_dir, mode)
        stem = _safe_name(entry.proposed_name or entry.path.stem)
        name = stem + entry.path.suffix.lower()
        dest = folder / name
        # Collision-safe without touching disk
        if dest in _seen:
            i = 1
            while True:
                candidate = folder / f'{stem}_{i}{entry.path.suffix.lower()}'
                if candidate not in _seen:
                    dest = candidate
                    break
                i += 1
        _seen.add(dest)
        moves.append((entry, dest))

    return moves


def apply_moves(
    moves: list[tuple[FileEntry, Path]],
    dry_run: bool = True,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> list[tuple[FileEntry, Path, bool, str]]:
    """Execute or simulate moves. Returns (entry, dest, success, message) per file."""
    results = []
    for i, (entry, dest) in enumerate(moves):
        if progress_cb:
            progress_cb(i, len(moves), entry.path.name)
        if dry_run:
            results.append((entry, dest, True, 'dry-run'))
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest_real = _unique_path(dest)
            shutil.move(str(entry.path), str(dest_real))
            results.append((entry, dest_real, True, 'moved'))
        except Exception as exc:
            results.append((entry, dest, False, str(exc)))
    return results
