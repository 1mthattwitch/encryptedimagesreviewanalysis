"""
Duplicate detection:
- Exact duplicates: MD5 hash match
- Near-duplicate images/videos: perceptual hash (phash) with configurable threshold
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .scanner import FileEntry


@dataclass
class DuplicateGroup:
    group_id: int
    kind: str           # "exact" or "near"
    entries: list["FileEntry"]

    @property
    def keep(self) -> "FileEntry":
        # Keep the largest (highest quality) copy, or first if equal
        return max(self.entries, key=lambda e: e.size_bytes)

    @property
    def removable(self) -> list["FileEntry"]:
        return [e for e in self.entries if e is not self.keep]

    @property
    def wasted_bytes(self) -> int:
        return sum(e.size_bytes for e in self.removable)


def _compute_phash(entry: "FileEntry") -> Optional[str]:
    if entry.phash:
        return entry.phash
    try:
        import imagehash
        from PIL import Image
        img = Image.open(entry.path)
        entry.phash = str(imagehash.phash(img))
        return entry.phash
    except Exception:
        return None


def _phash_distance(h1: str, h2: str) -> int:
    try:
        import imagehash
        return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)
    except Exception:
        return 999


def _video_keyframe(path: Path):
    """Return a PIL image of a keyframe from the video, or None."""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        from mediaorganizer import _quiet_stderr
        with _quiet_stderr():
            cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        target = min(int(total * 0.1), 30)  # 10% in, max frame 30
        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    except Exception:
        return None


def _compute_video_phash(entry: "FileEntry") -> Optional[str]:
    if entry.phash:
        return entry.phash
    try:
        import imagehash
        img = _video_keyframe(entry.path)
        if img is None:
            return None
        entry.phash = str(imagehash.phash(img))
        return entry.phash
    except Exception:
        return None


def find_duplicates(
    entries: list["FileEntry"],
    phash_threshold: int = 10,
) -> list[DuplicateGroup]:
    """Return duplicate groups. Mutates entry.md5 and entry.phash as a side effect."""
    from .scanner import compute_md5

    groups: list[DuplicateGroup] = []
    gid = 0

    # --- Exact duplicates by MD5 ---
    md5_buckets: dict[str, list["FileEntry"]] = defaultdict(list)
    for e in entries:
        compute_md5(e)
        if e.md5:
            md5_buckets[e.md5].append(e)

    exact_paths: set[Path] = set()
    for md5, dupes in md5_buckets.items():
        if len(dupes) > 1:
            groups.append(DuplicateGroup(group_id=gid, kind="exact", entries=dupes))
            gid += 1
            for e in dupes:
                exact_paths.add(e.path)

    # --- Near-duplicates (images and videos) by phash ---
    visual = [
        e for e in entries
        if e.file_type in ("image", "video") and e.path not in exact_paths
    ]

    # Compute phashes
    for e in visual:
        if e.file_type == "image":
            _compute_phash(e)
        else:
            _compute_video_phash(e)

    # Group by phash similarity (simple O(n²) for typical collection sizes)
    clustered: set[int] = set()
    for i, a in enumerate(visual):
        if i in clustered or not a.phash:
            continue
        cluster = [a]
        for j, b in enumerate(visual):
            if j <= i or j in clustered or not b.phash:
                continue
            if _phash_distance(a.phash, b.phash) <= phash_threshold:
                cluster.append(b)
                clustered.add(j)
        if len(cluster) > 1:
            clustered.add(i)
            groups.append(DuplicateGroup(group_id=gid, kind="near", entries=cluster))
            gid += 1

    return groups


def summary(groups: list[DuplicateGroup]) -> dict:
    total_exact = sum(1 for g in groups if g.kind == "exact")
    total_near = sum(1 for g in groups if g.kind == "near")
    wasted = sum(g.wasted_bytes for g in groups)
    return {
        "exact_groups": total_exact,
        "near_groups": total_near,
        "total_groups": len(groups),
        "wasted_bytes": wasted,
    }
