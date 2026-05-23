"""
Corrupted file detection, auto-rotation, timestamp fixer, secure delete.
"""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


# ── Corrupted file detection ─────────────────────────────────────────────────

def is_image_corrupt(path: Path) -> tuple[bool, str]:
    """Return (is_corrupt, reason). Tries full decode, not just header."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        # verify() closes the file; re-open to check pixel data
        with Image.open(path) as img:
            img.load()
        return False, ""
    except Exception as e:
        return True, str(e)


def is_video_corrupt(path: Path) -> tuple[bool, str]:
    try:
        from .ffmpeg_tools import find_ffmpeg
        import subprocess
        ff = find_ffmpeg()
        if not ff:
            return False, ""  # can't check without ffmpeg
        result = subprocess.run(
            [ff, "-v", "error", "-i", str(path), "-f", "null", "-"],
            capture_output=True, timeout=30,
        )
        errs = result.stderr.decode(errors="replace")
        if "Invalid data found" in errs or "moov atom not found" in errs:
            return True, errs[:200]
        return False, ""
    except Exception as e:
        return False, str(e)


def quarantine(entry: "FileEntry", quarantine_dir: Path) -> Path:
    """Move a corrupted file to a quarantine folder."""
    dest = quarantine_dir / entry.path.name
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(entry.path), str(dest))
    entry.path = dest
    return dest


def scan_corrupt(entries: list["FileEntry"], quarantine_dir: Path | None = None,
                 progress_cb=None) -> list["FileEntry"]:
    """Flag corrupted images/videos. Optionally quarantine them."""
    corrupt = []
    total = len(entries)
    for i, e in enumerate(entries):
        if e.file_type == "image":
            bad, reason = is_image_corrupt(e.path)
        elif e.file_type == "video":
            bad, reason = is_video_corrupt(e.path)
        else:
            bad, reason = False, ""
        if bad:
            e.health_ok = False
            if f"Corrupt: {reason[:80]}" not in e.health_issues:
                e.health_issues.append(f"Corrupt: {reason[:80]}")
            if quarantine_dir:
                quarantine(e, quarantine_dir)
            corrupt.append(e)
        if progress_cb:
            progress_cb(i + 1, total)
    return corrupt


# ── Timestamp fixer ──────────────────────────────────────────────────────────

def fix_timestamp(entry: "FileEntry") -> bool:
    """Set file mtime to EXIF date. Returns True if changed."""
    date = entry.exif_date or entry.date
    if not date:
        return False
    try:
        ts = date.timestamp()
        os.utime(entry.path, (ts, ts))
        return True
    except Exception:
        return False


def fix_all_timestamps(entries: list["FileEntry"]) -> int:
    return sum(1 for e in entries if fix_timestamp(e))


# ── Secure delete ────────────────────────────────────────────────────────────

def secure_delete(path: Path, passes: int = 3) -> bool:
    """Overwrite file with random bytes then delete. Returns True on success."""
    try:
        size = path.stat().st_size
        with open(path, "r+b") as f:
            for _ in range(passes):
                f.seek(0)
                f.write(random.randbytes(size))
                f.flush()
                os.fsync(f.fileno())
        path.unlink()
        return True
    except Exception:
        return False


# ── Stale file detection ─────────────────────────────────────────────────────

def find_stale(entries: list["FileEntry"], older_than_years: int = 5) -> list["FileEntry"]:
    """Return files with no EXIF date and mtime older than N years."""
    from datetime import datetime
    cutoff = datetime.now().replace(year=datetime.now().year - older_than_years)
    return [
        e for e in entries
        if not e.exif_date
        and e.date
        and e.date < cutoff
    ]
