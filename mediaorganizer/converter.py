"""
Image conversion utilities:
- HEIC/HEIF → JPG
- EXIF rotation fix (apply orientation tag physically)
- GPS/EXIF metadata strip
- Batch resize
- Format convert (PNG→JPG, WebP→JPG, etc.)
- Auto-enhance (levels + sharpen)
- Remove background (rembg, optional)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional


def _ensure_pillow_heif():
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
        return True
    except ImportError:
        return False


def convert_heic_to_jpg(src: Path, dest: Optional[Path] = None, quality: int = 90) -> Optional[Path]:
    if not _ensure_pillow_heif():
        raise ImportError("pillow-heif not installed. Run: pip install pillow-heif")
    from PIL import Image
    if dest is None:
        dest = src.with_suffix(".jpg")
    img = Image.open(src).convert("RGB")
    img.save(dest, format="JPEG", quality=quality)
    return dest


def batch_convert_heic(folder: Path, recursive: bool = True, quality: int = 90) -> list[Path]:
    pattern = "**/*.heic" if recursive else "*.heic"
    converted = []
    for p in folder.glob(pattern):
        try:
            out = convert_heic_to_jpg(p, quality=quality)
            if out:
                converted.append(out)
        except Exception:
            pass
    for p in folder.glob(pattern.replace("heic", "HEIC")):
        try:
            out = convert_heic_to_jpg(p, quality=quality)
            if out:
                converted.append(out)
        except Exception:
            pass
    return converted


def fix_rotation(src: Path, dest: Optional[Path] = None) -> Path:
    """Apply EXIF orientation tag physically and strip it."""
    from PIL import Image, ImageOps
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)
    out = dest or src
    fmt = img.format or "JPEG"
    if out.suffix.lower() in (".jpg", ".jpeg"):
        img.convert("RGB").save(out, format="JPEG", quality=92)
    else:
        img.save(out)
    return out


def strip_metadata(src: Path, dest: Optional[Path] = None,
                   strip_gps_only: bool = False) -> Path:
    """
    Remove GPS (and optionally all EXIF) metadata from an image.
    For videos, requires ffmpeg — see ffmpeg_tools.strip_video_metadata().
    """
    from PIL import Image
    img = Image.open(src)
    out = dest or src

    if strip_gps_only:
        # Re-save keeping non-GPS EXIF
        try:
            from PIL.ExifTags import TAGS
            exif = img.getexif()
            gps_ifd_tag = next((k for k, v in TAGS.items() if v == "GPSInfo"), None)
            if gps_ifd_tag and gps_ifd_tag in exif:
                del exif[gps_ifd_tag]
            img_bytes = img.tobytes()
            img2 = Image.frombytes(img.mode, img.size, img_bytes)
            img2.save(out, exif=exif.tobytes() if hasattr(exif, "tobytes") else b"")
        except Exception:
            # Fallback: strip all
            _save_no_exif(img, out)
    else:
        _save_no_exif(img, out)
    return out


def _save_no_exif(img, out: Path) -> None:
    from PIL import Image
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        clean.convert("RGB").save(out, format="JPEG", quality=92)
    else:
        clean.save(out)


def batch_resize(
    folder: Path,
    max_dimension: int = 1920,
    quality: int = 85,
    recursive: bool = True,
    exts: tuple = (".jpg", ".jpeg", ".png", ".webp"),
) -> list[Path]:
    """Resize all images in folder so no side exceeds max_dimension."""
    from PIL import Image
    pattern_fn = folder.rglob if recursive else folder.glob
    resized = []
    for ext in exts:
        for p in pattern_fn(f"*{ext}"):
            try:
                img = Image.open(p)
                if max(img.size) > max_dimension:
                    img.thumbnail((max_dimension, max_dimension))
                    if ext in (".jpg", ".jpeg"):
                        img.convert("RGB").save(p, format="JPEG", quality=quality)
                    else:
                        img.save(p)
                    resized.append(p)
            except Exception:
                pass
    return resized


def batch_convert_format(
    folder: Path,
    src_ext: str,
    dest_ext: str,
    quality: int = 90,
    recursive: bool = True,
) -> list[Path]:
    """Convert all src_ext files to dest_ext (e.g. PNG→JPG)."""
    from PIL import Image
    src_ext = src_ext.lower().lstrip(".")
    dest_ext = dest_ext.lower().lstrip(".")
    fmt_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP",
               "bmp": "BMP", "tiff": "TIFF", "gif": "GIF"}
    dest_fmt = fmt_map.get(dest_ext, dest_ext.upper())
    pattern_fn = folder.rglob if recursive else folder.glob
    converted = []
    for p in pattern_fn(f"*.{src_ext}"):
        dest = p.with_suffix(f".{dest_ext}")
        try:
            img = Image.open(p).convert("RGB")
            img.save(dest, format=dest_fmt, quality=quality)
            converted.append(dest)
        except Exception:
            pass
    return converted


def auto_enhance(src: Path, dest: Optional[Path] = None) -> Path:
    """Auto-levels + sharpen using Pillow."""
    from PIL import Image, ImageOps, ImageFilter
    img = Image.open(src).convert("RGB")
    img = ImageOps.autocontrast(img, cutoff=1)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=100, threshold=3))
    out = dest or src
    if out.suffix.lower() in (".jpg", ".jpeg"):
        img.save(out, format="JPEG", quality=92)
    else:
        img.save(out)
    return out


def remove_background(src: Path, dest: Optional[Path] = None) -> Path:
    """Remove image background using rembg (optional dep)."""
    try:
        from rembg import remove
        from PIL import Image
    except ImportError:
        raise ImportError("rembg not installed. Run: pip install rembg")
    img = Image.open(src)
    result = remove(img)
    out = dest or src.with_suffix(".png")
    result.save(out, format="PNG")
    return out
