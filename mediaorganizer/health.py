"""Per-type readability and corruption checks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .scanner import FileEntry


@dataclass
class HealthResult:
    ok: bool
    issues: list[str]


def check(entry: FileEntry) -> HealthResult:
    issues: list[str] = []

    if entry.size_bytes == 0:
        return HealthResult(ok=False, issues=['Empty file (0 bytes)'])

    if entry.file_type == 'image':
        _check_image(entry.path, issues)
    elif entry.file_type == 'video':
        _check_video(entry.path, issues)
    elif entry.file_type == 'pdf':
        _check_pdf(entry.path, issues)
    elif entry.file_type == 'document':
        _check_document(entry.path, issues)

    return HealthResult(ok=len(issues) == 0, issues=issues)


def _check_image(path: Path, issues: list[str]) -> None:
    try:
        from PIL import Image
        img = Image.open(path)
        img.verify()
        img = Image.open(path)  # re-open; verify() closes it
        w, h = img.size
        if w == 0 or h == 0:
            issues.append(f'Zero-dimension image ({w}x{h})')
    except Exception as e:
        issues.append(f'Cannot open image: {e}')


def _check_video(path: Path, issues: list[str]) -> None:
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            issues.append('Cannot open video file')
        else:
            fc = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if fc <= 0:
                issues.append('Video has no frames')
        cap.release()
    except Exception as e:
        issues.append(f'Cannot read video: {e}')


def _check_pdf(path: Path, issues: list[str]) -> None:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        if doc.page_count == 0:
            issues.append('PDF has no pages')
        doc.close()
    except Exception as e:
        issues.append(f'Cannot open PDF: {e}')


def _check_document(path: Path, issues: list[str]) -> None:
    try:
        if path.suffix.lower() == '.docx':
            from docx import Document
            doc = Document(str(path))
            text = '\n'.join(p.text for p in doc.paragraphs)
        else:
            text = path.read_text(errors='replace')
        if not text.strip():
            issues.append('Document appears empty')
    except Exception as e:
        issues.append(f'Cannot read document: {e}')
