"""File discovery, type detection, and metadata extraction."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif'}
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp'}
PDF_EXTS = {'.pdf'}
DOC_EXTS = {'.txt', '.md', '.rst', '.log', '.docx', '.odt', '.doc'}

_MAGIC: list[tuple[bytes, int, str]] = [
    (b'\xff\xd8\xff', 0, 'image'),
    (b'\x89PNG\r\n\x1a\n', 0, 'image'),
    (b'GIF8', 0, 'image'),
    (b'BM', 0, 'image'),
    (b'II*\x00', 0, 'image'),
    (b'MM\x00*', 0, 'image'),
    (b'%PDF', 0, 'pdf'),
    (b'\x1aE\xdf\xa3', 0, 'video'),
    (b'RIFF', 0, 'video'),
    (b'ftyp', 4, 'video'),
]


@dataclass
class FileEntry:
    path: Path
    file_type: str
    size_bytes: int
    date: Optional[datetime]
    metadata: dict = field(default_factory=dict)
    content_hash: str = ''
    ai_description: str = ''
    ai_category: str = ''
    proposed_name: str = ''
    health_ok: bool = True
    health_issues: list = field(default_factory=list)
    is_duplicate: bool = False
    duplicate_group: str = ''


def _detect_type_by_magic(path: Path) -> Optional[str]:
    try:
        with open(path, 'rb') as f:
            header = f.read(16)
        for magic, offset, ftype in _MAGIC:
            if header[offset:offset + len(magic)] == magic:
                return ftype
    except OSError:
        pass
    return None


def _ext_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return 'image'
    if ext in VIDEO_EXTS:
        return 'video'
    if ext in PDF_EXTS:
        return 'pdf'
    if ext in DOC_EXTS:
        return 'document'
    return 'unknown'


def _exif_date(path: Path) -> Optional[datetime]:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(path)
        exif = img._getexif()  # type: ignore[attr-defined]
        if exif:
            for tag_id, val in exif.items():
                if TAGS.get(tag_id) == 'DateTimeOriginal' and isinstance(val, str):
                    return datetime.strptime(val, '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
    return None


def _video_metadata(path: Path) -> dict:
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return {}
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0
        cap.release()
        return {'fps': fps, 'frame_count': frame_count, 'width': width, 'height': height, 'duration_s': round(duration, 1)}
    except Exception:
        return {}


def _file_date(path: Path, file_type: str) -> Optional[datetime]:
    if file_type == 'image':
        d = _exif_date(path)
        if d:
            return d
    try:
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime)
    except OSError:
        return None


def scan(root: Path, recursive: bool = True) -> list[FileEntry]:
    """Walk root and return a FileEntry for every file found."""
    entries: list[FileEntry] = []
    glob = root.rglob('*') if recursive else root.glob('*')
    for p in sorted(glob):
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        ext_type = _ext_type(p)
        magic_type = _detect_type_by_magic(p)
        file_type = magic_type or ext_type
        metadata = _video_metadata(p) if file_type == 'video' else {}
        date = _file_date(p, file_type)
        entries.append(FileEntry(
            path=p,
            file_type=file_type,
            size_bytes=size,
            date=date,
            metadata=metadata,
        ))
    return entries
