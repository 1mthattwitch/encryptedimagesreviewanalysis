"""
File discovery, type detection by magic bytes, EXIF/video metadata extraction.
Returns a list of FileEntry dataclasses.
"""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Magic-byte signatures: (offset, bytes) → type
_MAGIC: list[tuple[int, bytes, str]] = [
    (0, b"\xff\xd8\xff", "image"),          # JPEG
    (0, b"\x89PNG\r\n\x1a\n", "image"),     # PNG
    (0, b"GIF8", "image"),                   # GIF
    (0, b"RIFF", "image"),                   # WEBP (also checked below)
    (0, b"BM", "image"),                     # BMP
    (0, b"\x00\x00\x01\x00", "image"),      # ICO
    (0, b"II\x2a\x00", "image"),            # TIFF LE
    (0, b"MM\x00\x2a", "image"),            # TIFF BE
    (0, b"\x00\x00\x00\x0cftyp", "video"),  # MP4/MOV (sometimes)
    (4, b"ftyp", "video"),                   # MP4/MOV/M4V
    (0, b"\x1a\x45\xdf\xa3", "video"),      # MKV/WebM
    (0, b"RIFF", "video"),                   # AVI (also WEBP — resolved by ext)
    (0, b"OggS", "video"),                   # OGG video
    (0, b"\x00\x00\x01\xb3", "video"),      # MPEG video
    (0, b"\x00\x00\x01\xba", "video"),      # MPEG PS
    (0, b"%PDF", "pdf"),
    (0, b"PK\x03\x04", "document"),         # ZIP-based (docx, odt, xlsx…)
    (0, b"\xd0\xcf\x11\xe0", "document"),   # OLE2 (old .doc, .xls)
    (0, b"\xef\xbb\xbf", "document"),       # UTF-8 BOM text
]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",
              ".heic", ".heif", ".avif", ".ico", ".jfif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v",
              ".3gp", ".ts", ".mts", ".mpeg", ".mpg", ".ogv"}
AUDIO_EXTS = {".mp3", ".aac", ".wav", ".flac", ".ogg", ".m4a", ".wma", ".opus"}
DOC_EXTS   = {".pdf", ".docx", ".doc", ".odt", ".txt", ".md", ".rst", ".log",
              ".csv", ".xlsx", ".xls", ".ods", ".rtf", ".pages"}


@dataclass
class FileEntry:
    path: Path
    file_type: str          # image / video / audio / pdf / document / other
    size_bytes: int
    mime_ext: str           # lower-case extension without dot
    date: Optional[datetime] = None
    exif_date: Optional[datetime] = None
    gps: Optional[tuple[float, float]] = None   # (lat, lon)
    camera: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_s: Optional[float] = None
    fps: Optional[float] = None
    ai_description: Optional[str] = None
    ai_category: Optional[str] = None
    proposed_name: Optional[str] = None
    health_ok: bool = True
    health_issues: list[str] = field(default_factory=list)
    md5: Optional[str] = None
    phash: Optional[str] = None
    quality_grade: Optional[str] = None        # A/B/C/D/F
    quality_blur: Optional[float] = None
    quality_exposure: Optional[float] = None
    face_count: Optional[int] = None
    ocr_text: Optional[str] = None
    transcript: Optional[str] = None
    metadata: dict = field(default_factory=dict)


def _read_magic(path: Path, n: int = 16) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def _type_from_magic(magic: bytes, ext: str) -> str:
    for offset, sig, ftype in _MAGIC:
        chunk = magic[offset:offset + len(sig)]
        if chunk == sig:
            # Disambiguate RIFF: WEBP vs AVI
            if sig == b"RIFF":
                if magic[8:12] == b"WEBP" or ext in (".webp",):
                    return "image"
                return "video"
            return ftype
    return None


def _detect_type(path: Path) -> str:
    ext = path.suffix.lower()
    magic = _read_magic(path)
    by_magic = _type_from_magic(magic, ext)
    if by_magic:
        return by_magic
    # Fall back to extension
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext == ".pdf":
        return "pdf"
    if ext in DOC_EXTS:
        return "document"
    return "other"


def _exif_date(path: Path):
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(path)
        exif_data = img._getexif()
        if not exif_data:
            return None
        tag_map = {v: k for k, v in TAGS.items()}
        for tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            tag_id = tag_map.get(tag_name)
            if tag_id and tag_id in exif_data:
                val = exif_data[tag_id]
                try:
                    return datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass
    except Exception:
        pass
    return None


def _exif_gps(path: Path) -> Optional[tuple[float, float]]:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
        img = Image.open(path)
        exif_data = img._getexif()
        if not exif_data:
            return None
        tag_map = {v: k for k, v in TAGS.items()}
        gps_id = tag_map.get("GPSInfo")
        if not gps_id or gps_id not in exif_data:
            return None
        gps_info = {GPSTAGS.get(k, k): v for k, v in exif_data[gps_id].items()}

        def _dms(vals):
            d, m, s = [float(v) for v in vals]
            return d + m / 60 + s / 3600

        lat = _dms(gps_info.get("GPSLatitude", [0, 0, 0]))
        lon = _dms(gps_info.get("GPSLongitude", [0, 0, 0]))
        if gps_info.get("GPSLatitudeRef", "N") == "S":
            lat = -lat
        if gps_info.get("GPSLongitudeRef", "E") == "W":
            lon = -lon
        return (lat, lon) if lat or lon else None
    except Exception:
        return None


def _exif_camera(path: Path) -> Optional[str]:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(path)
        exif_data = img._getexif()
        if not exif_data:
            return None
        tag_map = {v: k for k, v in TAGS.items()}
        make_id = tag_map.get("Make")
        model_id = tag_map.get("Model")
        make = exif_data.get(make_id, "").strip() if make_id else ""
        model = exif_data.get(model_id, "").strip() if model_id else ""
        parts = []
        if make and make not in model:
            parts.append(make)
        if model:
            parts.append(model)
        return " ".join(parts) or None
    except Exception:
        return None


def _image_dims(path: Path) -> tuple[Optional[int], Optional[int]]:
    try:
        from PIL import Image
        img = Image.open(path)
        return img.size  # (width, height)
    except Exception:
        return None, None


def _video_meta(path: Path) -> tuple[Optional[int], Optional[int], Optional[float], Optional[float]]:
    try:
        import cv2
        from mediaorganizer import _quiet_stderr
        with _quiet_stderr():
            cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None, None, None, None
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps if fps > 0 else None
        cap.release()
        return w or None, h or None, duration, fps or None
    except Exception:
        return None, None, None, None


def _mtime(path: Path) -> Optional[datetime]:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts)
    except Exception:
        return None


def scan(folder: Path, recursive: bool = True) -> list[FileEntry]:
    """Walk *folder* and return a FileEntry for every file found."""
    entries: list[FileEntry] = []
    walk = folder.rglob("*") if recursive else folder.glob("*")
    for p in walk:
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            size = 0

        ftype = _detect_type(p)
        ext = p.suffix.lower().lstrip(".")
        entry = FileEntry(path=p, file_type=ftype, size_bytes=size, mime_ext=ext)

        mtime = _mtime(p)
        entry.date = mtime

        if ftype == "image":
            entry.exif_date = _exif_date(p)
            if entry.exif_date:
                entry.date = entry.exif_date
            entry.gps = _exif_gps(p)
            entry.camera = _exif_camera(p)
            entry.width, entry.height = _image_dims(p)

        elif ftype == "video":
            entry.width, entry.height, entry.duration_s, entry.fps = _video_meta(p)

        entries.append(entry)

    return entries


def compute_md5(entry: FileEntry) -> str:
    if entry.md5:
        return entry.md5
    h = hashlib.md5()
    try:
        with open(entry.path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        entry.md5 = h.hexdigest()
    except OSError:
        entry.md5 = ""
    return entry.md5
