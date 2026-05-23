"""
OCR text extraction from images using Tesseract (optional dep).
Falls back gracefully with a clear install message if not available.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry

_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
]


def find_tesseract() -> Optional[str]:
    found = shutil.which("tesseract")
    if found:
        return found
    for p in _TESSERACT_PATHS:
        if Path(p).is_file():
            return p
    return None


def is_available() -> bool:
    return find_tesseract() is not None


def extract_text(path: Path, lang: str = "eng") -> str:
    """
    Extract text from an image using pytesseract (preferred) or
    subprocess call to tesseract binary.
    Returns empty string if unavailable or extraction fails.
    """
    # Try pytesseract first
    try:
        import pytesseract
        from PIL import Image
        tess = find_tesseract()
        if tess:
            pytesseract.pytesseract.tesseract_cmd = tess
        img = Image.open(path)
        return pytesseract.image_to_string(img, lang=lang).strip()
    except ImportError:
        pass
    except Exception:
        return ""

    # Fallback: subprocess
    tess = find_tesseract()
    if not tess:
        return ""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        out_base = f.name[:-4]  # tesseract appends .txt itself
    try:
        subprocess.run(
            [tess, str(path), out_base, "-l", lang],
            capture_output=True, timeout=30,
        )
        txt_path = Path(out_base + ".txt")
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
            txt_path.unlink(missing_ok=True)
            return text
    except Exception:
        pass
    return ""


def extract_entry(entry: "FileEntry") -> None:
    """Populate entry.ocr_text in-place."""
    if entry.file_type != "image":
        return
    entry.ocr_text = extract_text(entry.path) or None


def extract_all(entries: list["FileEntry"], progress_cb=None) -> None:
    total = len(entries)
    for i, e in enumerate(entries):
        extract_entry(e)
        if progress_cb:
            progress_cb(i + 1, total)
