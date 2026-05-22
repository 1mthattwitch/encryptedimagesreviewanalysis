"""
Group photos into time-based events by EXIF capture date.
Photos within gap_minutes of each other are in the same event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


@dataclass
class EventGroup:
    event_id: int
    start: datetime
    end: datetime
    entries: list["FileEntry"] = field(default_factory=list)
    name: str = ""

    @property
    def auto_name(self) -> str:
        hour = self.start.hour
        if hour < 12:
            tod = "morning"
        elif hour < 17:
            tod = "afternoon"
        else:
            tod = "evening"
        date_str = self.start.strftime("%Y-%m-%d")
        return f"{date_str} {tod} ({len(self.entries)} photos)"

    @property
    def display_name(self) -> str:
        return self.name or self.auto_name


def group_by_events(
    entries: list["FileEntry"],
    gap_minutes: int = 60,
) -> list[EventGroup]:
    """
    Sort entries by capture date and split into events where the gap
    between consecutive photos exceeds gap_minutes.
    Entries with no date are placed in a single 'Undated' group.
    """
    dated = sorted(
        [e for e in entries if e.date and e.file_type in ("image", "video")],
        key=lambda e: e.date,
    )
    undated = [e for e in entries if not e.date and e.file_type in ("image", "video")]

    groups: list[EventGroup] = []
    gid = 0
    gap = timedelta(minutes=gap_minutes)

    if dated:
        current = EventGroup(event_id=gid, start=dated[0].date, end=dated[0].date)
        current.entries.append(dated[0])
        for entry in dated[1:]:
            if entry.date - current.end <= gap:
                current.entries.append(entry)
                current.end = entry.date
            else:
                groups.append(current)
                gid += 1
                current = EventGroup(event_id=gid, start=entry.date, end=entry.date)
                current.entries.append(entry)
        groups.append(current)

    if undated:
        gid += 1
        ug = EventGroup(event_id=gid,
                        start=datetime(1970, 1, 1),
                        end=datetime(1970, 1, 1),
                        name=f"Undated ({len(undated)} files)")
        ug.entries = undated
        groups.append(ug)

    return groups
