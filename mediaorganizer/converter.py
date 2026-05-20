"""Image conversion, rotation fix, GPS strip, and batch resize tools."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PIL import Image

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False

_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'}
_HEIC_EXTS = {'.heic', '.heif', '.hif'}


def heic_to_jpg(src: Path, dest_dir: Optional[Path] = None, quality: int = 92) -> Path:
    """Convert one HEIC/HEIF file to JPEG. Returns the new path."""
    if not HEIF_AVAILABLE:
        raise RuntimeError('pillow-heif not installed. Run: pip install pillow-heif')
    dest_dir = dest_dir or src.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (src.stem + '.jpg')
    n = 1
    while dest.exists():
        dest = dest_dir / f'{src.stem}_{n}.jpg'
        n += 1
    img = Image.open(src).convert('RGB')
    img.save(dest, 'JPEG', quality=quality)
    return dest


def batch_heic_to_jpg(
    folder: Path,
    recursive: bool = True,
    quality: int = 92,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> list:
    """Convert all HEIC/HEIF files in folder to JPEG. Returns (src, dest) pairs."""
    if not HEIF_AVAILABLE:
        raise RuntimeError('pillow-heif not installed. Run: pip install pillow-heif')
    paths = list(folder.rglob('*') if recursive else folder.iterdir())
    paths = [p for p in paths if p.suffix.lower() in _HEIC_EXTS]
    results = []
    for i, src in enumerate(paths):
        if progress:
            progress(i, len(paths), src.name)
        try:
            results.append((src, heic_to_jpg(src, quality=quality)))
        except Exception:
            pass
    if progress and paths:
        progress(len(paths), len(paths), 'Done')
    return results


def fix_exif_rotation(src: Path, in_place: bool = True, dest: Optional[Path] = None) -> Path:
    """Rotate pixel data to match EXIF orientation tag, then reset the tag."""
    img = Image.open(src)
    orig_fmt = img.format
    try:
        exif_data = img._getexif() or {}  # type: ignore[attr-defined]
    except Exception:
        exif_data = {}
    orient = exif_data.get(274, 1)  # 274 = Orientation tag
    if orient == 2:   img = img.transpose(Image.FLIP_LEFT_RIGHT)
    elif orient == 3: img = img.rotate(180)
    elif orient == 4: img = img.transpose(Image.FLIP_TOP_BOTTOM)
    elif orient == 5: img = img.rotate(270, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    elif orient == 6: img = img.rotate(270, expand=True)
    elif orient == 7: img = img.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    elif orient == 8: img = img.rotate(90, expand=True)
    out = src if (in_place and dest is None) else (dest or src)
    fmt = (orig_fmt or src.suffix.lstrip('.').upper() or 'JPEG').upper()
    if fmt == 'JPG': fmt = 'JPEG'
    kwargs: dict = {'quality': 92} if fmt == 'JPEG' else {}
    try:
        new_exif = img.getexif()
        new_exif[274] = 1
        kwargs['exif'] = new_exif.tobytes()
    except Exception:
        pass
    img.save(out, format=fmt, **kwargs)
    return out


def strip_gps(src: Path, in_place: bool = True, dest: Optional[Path] = None) -> Path:
    """Remove GPS location data from image EXIF. Modifies in-place by default."""
    img = Image.open(src)
    orig_fmt = img.format
    out = src if (in_place and dest is None) else (dest or src)
    fmt = (orig_fmt or src.suffix.lstrip('.').upper() or 'JPEG').upper()
    if fmt == 'JPG': fmt = 'JPEG'
    kwargs: dict = {'quality': 92} if fmt == 'JPEG' else {}
    GPS_IFD = 34853
    try:
        exif = img.getexif()
        if GPS_IFD in exif:
            del exif[GPS_IFD]
        ifd = exif.get_ifd(GPS_IFD)
        ifd.clear()
        kwargs['exif'] = exif.tobytes()
    except Exception:
        pass
    img.save(out, format=fmt, **kwargs)
    return out


def batch_resize(
    folder: Path,
    max_dimension: int = 1920,
    quality: int = 88,
    recursive: bool = True,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> list:
    """Shrink images so the longest side <= max_dimension. Returns list of modified paths."""
    paths = list(folder.rglob('*') if recursive else folder.iterdir())
    paths = [p for p in paths if p.suffix.lower() in _IMAGE_EXTS]
    modified = []
    for i, path in enumerate(paths):
        if progress:
            progress(i, len(paths), path.name)
        try:
            img = Image.open(path)
            w, h = img.size
            if max(w, h) <= max_dimension:
                continue
            orig_fmt = img.format
            scale = max_dimension / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            fmt = (orig_fmt or path.suffix.lstrip('.').upper() or 'JPEG').upper()
            if fmt == 'JPG': fmt = 'JPEG'
            kwargs = {'quality': quality} if fmt == 'JPEG' else {}
            img.save(path, format=fmt, **kwargs)
            modified.append(path)
        except Exception:
            pass
    if progress and paths:
        progress(len(paths), len(paths), 'Done')
    return modified
