"""
Per-file readability and corruption checks.
Returns a HealthResult for each FileEntry.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


@dataclass
class HealthResult:
    ok: bool
    issues: list[str]


def check(entry: "FileEntry") -> HealthResult:
    path = entry.path
    issues: list[str] = []

    if entry.size_bytes == 0:
        return HealthResult(ok=False, issues=["Empty file (0 bytes)"])

    ftype = entry.file_type

    if ftype == "image":
        issues.extend(_check_image(path))
    elif ftype == "video":
        issues.extend(_check_video(path))
    elif ftype == "pdf":
        issues.extend(_check_pdf(path))
    elif ftype == "document":
        issues.extend(_check_document(path))
    else:
        # Generic: just confirm readable
        try:
            with open(path, "rb") as f:
                f.read(256)
        except OSError as e:
            issues.append(f"Cannot read: {e}")

    return HealthResult(ok=len(issues) == 0, issues=issues)


def _check_image(path: Path) -> list[str]:
    issues = []
    try:
        from PIL import Image, UnidentifiedImageError
        try:
            img = Image.open(path)
            img.verify()
        except UnidentifiedImageError:
            issues.append("Unrecognised image format")
            return issues
        except Exception as e:
            issues.append(f"Image verify failed: {e}")
            return issues

        # Re-open after verify (verify closes the file)
        try:
            img2 = Image.open(path)
            w, h = img2.size
            if w == 0 or h == 0:
                issues.append("Zero-dimension image")
        except Exception as e:
            issues.append(f"Cannot read image dimensions: {e}")
    except ImportError:
        pass
    return issues


def _check_video(path: Path) -> list[str]:
    issues = []
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            issues.append("OpenCV cannot open video")
        else:
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if frame_count <= 0:
                issues.append("Video has no frames")
            ok, _ = cap.read()
            if not ok:
                issues.append("Cannot decode first frame")
        cap.release()
    except ImportError:
        pass
    return issues


def _check_pdf(path: Path) -> list[str]:
    issues = []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        if doc.page_count == 0:
            issues.append("PDF has no pages")
        doc.close()
    except Exception as e:
        issues.append(f"PDF unreadable: {e}")
    return issues


def _check_document(path: Path) -> list[str]:
    issues = []
    ext = path.suffix.lower()
    try:
        if ext in (".docx",):
            import docx
            docx.Document(str(path))
        elif ext in (".odt",):
            import odf.opendocument
            odf.opendocument.load(str(path))
        else:
            # Plain text — just read it
            path.read_text(errors="replace")
    except Exception as e:
        issues.append(f"Document unreadable: {e}")
    return issues


def check_all(entries: list["FileEntry"], progress_cb=None) -> None:
    """Run health check on every entry, mutating entry.health_ok and entry.health_issues in-place."""
    total = len(entries)
    for i, entry in enumerate(entries):
        result = check(entry)
        entry.health_ok = result.ok
        entry.health_issues = result.issues
        if progress_cb:
            progress_cb(i + 1, total)
