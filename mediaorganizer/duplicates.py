"""Exact (MD5) and near-duplicate (perceptual hash) detection."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from .scanner import FileEntry


def compute_md5(path: Path) -> str:
    h = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ''


def _image_phash(path: Path):
    try:
        import imagehash
        from PIL import Image
        return imagehash.phash(Image.open(path))
    except Exception:
        return None


def _video_phash(path: Path):
    try:
        import cv2
        import imagehash
        from PIL import Image
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 5))
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return imagehash.phash(Image.fromarray(rgb))
    except Exception:
        return None


def _near_dupe_pass(
    entries: list[FileEntry],
    hash_fn,
    prefix: str,
    threshold: int,
    out: dict[str, list[FileEntry]],
) -> None:
    pairs: list[tuple[FileEntry, object]] = []
    for e in entries:
        h = hash_fn(e.path)
        if h is not None:
            pairs.append((e, h))

    used: set[int] = set()
    for i, (e1, h1) in enumerate(pairs):
        if i in used:
            continue
        group = [e1]
        for j, (e2, h2) in enumerate(pairs):
            if j <= i or j in used:
                continue
            if (h1 - h2) <= threshold:
                group.append(e2)
                used.add(j)
        if len(group) > 1:
            used.add(i)
            key = f'{prefix}_near_{i}'
            out[key] = group
            for e in group:
                e.is_duplicate = True
                e.duplicate_group = key


def find_duplicates(
    entries: list[FileEntry],
    phash_threshold: int = 10,
) -> dict[str, list[FileEntry]]:
    """Return groups dict: group_key -> list[FileEntry]. Only groups with 2+ members included."""
    md5_groups: dict[str, list[FileEntry]] = {}
    for e in entries:
        if e.size_bytes == 0:
            continue
        h = compute_md5(e.path)
        if not h:
            continue
        e.content_hash = h
        md5_groups.setdefault(h, []).append(e)

    result: dict[str, list[FileEntry]] = {}
    for h, group in md5_groups.items():
        if len(group) > 1:
            key = f'exact_{h[:8]}'
            result[key] = group
            for e in group:
                e.is_duplicate = True
                e.duplicate_group = key

    images = [e for e in entries if e.file_type == 'image' and not e.is_duplicate]
    videos = [e for e in entries if e.file_type == 'video' and not e.is_duplicate]
    _near_dupe_pass(images, _image_phash, 'img', phash_threshold, result)
    _near_dupe_pass(videos, _video_phash, 'vid', phash_threshold, result)
    return result
