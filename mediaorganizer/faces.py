"""
Face detection using OpenCV Haar cascades (no extra deps).
Provides blur/anonymise and face count for AI category improvement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry

_CASCADE_CACHE = None


def _cascade():
    global _CASCADE_CACHE
    if _CASCADE_CACHE is not None:
        return _CASCADE_CACHE
    import cv2
    path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    _CASCADE_CACHE = cv2.CascadeClassifier(path)
    return _CASCADE_CACHE


def detect_faces(path: Path) -> list[tuple[int, int, int, int]]:
    """Return list of (x, y, w, h) face rectangles."""
    try:
        import cv2
        img = cv2.imread(str(path))
        if img is None:
            return []
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cascade = _cascade()
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                          minSize=(30, 30))
        if len(faces) == 0:
            return []
        return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]
    except Exception:
        return []


def count_faces(path: Path) -> int:
    return len(detect_faces(path))


def blur_faces(src: Path, dest: Optional[Path] = None, blur_radius: int = 25) -> Path:
    """Gaussian-blur every detected face and save result."""
    import cv2
    img = cv2.imread(str(src))
    if img is None:
        raise ValueError(f"Cannot open image: {src}")
    faces = detect_faces(src)
    for x, y, w, h in faces:
        roi = img[y:y+h, x:x+w]
        ksize = blur_radius * 2 + 1  # must be odd
        blurred = cv2.GaussianBlur(roi, (ksize, ksize), 0)
        img[y:y+h, x:x+w] = blurred
    out = dest or src
    cv2.imwrite(str(out), img)
    return out


def anonymise_faces(src: Path, dest: Optional[Path] = None) -> Path:
    """Replace each face with a solid coloured rectangle (stronger than blur)."""
    import cv2
    img = cv2.imread(str(src))
    if img is None:
        raise ValueError(f"Cannot open image: {src}")
    faces = detect_faces(src)
    for i, (x, y, w, h) in enumerate(faces):
        color = [(80, 80, 200), (200, 80, 80), (80, 200, 80)][i % 3]
        img[y:y+h, x:x+w] = color
    out = dest or src
    cv2.imwrite(str(out), img)
    return out


def update_entry_face_count(entry: "FileEntry") -> None:
    if entry.file_type != "image":
        return
    n = count_faces(entry.path)
    entry.face_count = n
    # Improve AI category if not already set by Ollama
    if n == 1 and entry.ai_category in (None, "Other"):
        entry.ai_category = "Selfies"
    elif n >= 2 and entry.ai_category in (None, "Other"):
        entry.ai_category = "People"
