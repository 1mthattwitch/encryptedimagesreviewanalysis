"""
File organization: move files into structured folders.
Three modes: type, date, content (AI category).
Supports dry-run, move history, and undo.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .scanner import FileEntry

# WhatsApp / Telegram / screenshot detection patterns
_WA_RE = re.compile(r"img[-_]\d{8}[-_]wa\d+", re.IGNORECASE)
_TG_RE = re.compile(r"photo_\d+_\d+", re.IGNORECASE)
_SCREEN_RESOLUTIONS = {
    (1080, 1920), (1080, 2160), (1080, 2340), (1080, 2400),
    (1170, 2532), (1284, 2778), (828, 1792),  # iPhones
    (720, 1280), (1440, 2560), (1440, 3040),
    (1440, 3200), (412, 892),   # common Android
}


def _sanitize(name: str, max_len: int = 80) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^\w\s\-]", " ", name)
    name = re.sub(r"\s+", "_", name.strip()).strip("_-")
    return name[:max_len] or "unnamed"


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    i = 1
    while True:
        cand = parent / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1


def _is_screenshot(entry: "FileEntry") -> bool:
    if entry.width and entry.height:
        pair = (min(entry.width, entry.height), max(entry.width, entry.height))
        if pair in _SCREEN_RESOLUTIONS:
            return True
    return "screenshot" in entry.path.name.lower()


def _app_source(entry: "FileEntry") -> Optional[str]:
    name = entry.path.name
    if _WA_RE.search(name):
        return "WhatsApp"
    if _TG_RE.search(name):
        return "Telegram"
    if _is_screenshot(entry):
        return "Screenshots"
    return None


def _dest_type(entry: "FileEntry", output: Path) -> Path:
    type_map = {
        "image": "Images", "video": "Videos", "audio": "Audio",
        "pdf": "PDFs", "document": "Documents", "other": "Other",
    }
    folder = type_map.get(entry.file_type, "Other")
    if not entry.health_ok:
        folder = "Unreadable"
    return output / folder / entry.path.name


def _dest_date(entry: "FileEntry", output: Path) -> Path:
    date = entry.date or datetime.now()
    type_map = {
        "image": "Images", "video": "Videos", "audio": "Audio",
        "pdf": "PDFs", "document": "Documents", "other": "Other",
    }
    folder = type_map.get(entry.file_type, "Other")
    if not entry.health_ok:
        return output / "Unreadable" / entry.path.name
    return output / folder / str(date.year) / f"{date.month:02d}" / entry.path.name


def _dest_content(entry: "FileEntry", output: Path) -> Path:
    category = entry.ai_category or "Other"
    safe_cat = _sanitize(category)
    if not entry.health_ok:
        safe_cat = "Unreadable"
    return output / safe_cat / entry.path.name


def _dest_event(entry: "FileEntry", output: Path,
                event_name: Optional[str] = None) -> Path:
    date = entry.date or datetime.now()
    label = event_name or date.strftime("%Y-%m-%d")
    return output / "Events" / _sanitize(label) / entry.path.name


def plan_moves(
    entries: list["FileEntry"],
    output: Path,
    mode: str = "type",
    event_name: Optional[str] = None,
) -> list[tuple["FileEntry", Path]]:
    """Return (entry, dest) pairs without moving anything."""
    moves = []
    for entry in entries:
        if mode == "type":
            dest = _dest_type(entry, output)
        elif mode == "date":
            dest = _dest_date(entry, output)
        elif mode == "content":
            dest = _dest_content(entry, output)
        elif mode == "event":
            dest = _dest_event(entry, output, event_name)
        else:
            dest = _dest_type(entry, output)
        dest = _unique(dest)
        moves.append((entry, dest))
    return moves


def apply_moves(
    moves: list[tuple["FileEntry", Path]],
    log_path: Optional[Path] = None,
) -> list[dict]:
    """Execute moves, write move_log.json if log_path given. Returns log records."""
    records = []
    for entry, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(entry.path), str(dest))
            records.append({
                "timestamp": datetime.now().isoformat(),
                "src": str(entry.path),
                "dest": str(dest),
                "ok": True,
            })
            entry.path = dest  # update in-memory reference
        except Exception as e:
            records.append({
                "timestamp": datetime.now().isoformat(),
                "src": str(entry.path),
                "dest": str(dest),
                "ok": False,
                "error": str(e),
            })

    if log_path:
        existing = []
        if log_path.exists():
            try:
                existing = json.loads(log_path.read_text())
            except Exception:
                existing = []
        existing.extend(records)
        log_path.write_text(json.dumps(existing, indent=2))

    return records


def undo_last_run(log_path: Path) -> list[dict]:
    """Reverse the most recent batch recorded in move_log.json."""
    if not log_path.exists():
        return []
    records = json.loads(log_path.read_text())
    if not records:
        return []

    # Find the last batch (records with the same date prefix in timestamp)
    # Simple approach: undo all records from the last minute
    last_ts = records[-1]["timestamp"]
    last_minute = last_ts[:16]  # "YYYY-MM-DDTHH:MM"
    batch = [r for r in records if r["timestamp"][:16] == last_minute and r["ok"]]

    undo_records = []
    for r in reversed(batch):
        src, dest = Path(r["dest"]), Path(r["src"])
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            undo_records.append({"src": str(src), "dest": str(dest), "ok": True})
        except Exception as e:
            undo_records.append({"src": str(src), "dest": str(dest),
                                  "ok": False, "error": str(e)})

    # Remove undone records from log
    remaining = [r for r in records if r["timestamp"][:16] != last_minute]
    log_path.write_text(json.dumps(remaining, indent=2))
    return undo_records


def sort_by_app_source(
    entries: list["FileEntry"],
    output: Path,
    apply: bool = False,
) -> list[tuple["FileEntry", Path]]:
    """Move WhatsApp/Telegram/Screenshot files to dedicated folders."""
    moves = []
    for entry in entries:
        source = _app_source(entry)
        if source:
            dest = _unique(output / source / entry.path.name)
            moves.append((entry, dest))
    if apply:
        apply_moves(moves)
    return moves
