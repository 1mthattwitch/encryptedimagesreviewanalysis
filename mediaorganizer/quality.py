"""
Offline photo quality scoring using OpenCV + numpy (already required).
Grades: A (excellent) / B (good) / C (average) / D (poor) / F (very poor)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


@dataclass
class QualityResult:
    blur_score: float       # higher = sharper (Laplacian variance)
    exposure_score: float   # 0-1, 1 = well-exposed
    noise_score: float      # 0-1, 1 = low noise
    pixels: int             # total pixel count
    grade: str              # A/B/C/D/F


def _blur_score(gray) -> float:
    """Laplacian variance — higher means sharper."""
    import cv2
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var())


def _exposure_score(gray) -> float:
    """Histogram analysis — penalise clipped highlights or crushed shadows."""
    import numpy as np
    hist, _ = np.histogram(gray.flatten(), bins=256, range=(0, 256))
    total = gray.size
    clipped_hi = hist[250:].sum() / total
    clipped_lo = hist[:5].sum() / total
    penalty = clipped_hi + clipped_lo
    return max(0.0, 1.0 - penalty * 5)


def _noise_score(gray) -> float:
    """Estimate noise by high-frequency energy in dark regions."""
    import cv2
    import numpy as np
    dark_mask = gray < 80
    if dark_mask.sum() < 100:
        return 0.8  # not enough dark pixels to judge
    dark = gray[dark_mask].astype(float)
    std = dark.std()
    # std < 5 → very clean; std > 30 → very noisy
    return max(0.0, min(1.0, 1.0 - (std - 5) / 25))


def _grade(blur: float, exposure: float, noise: float, pixels: int) -> str:
    score = 0
    # Blur contribution (0-40 pts)
    if blur > 500:
        score += 40
    elif blur > 200:
        score += 30
    elif blur > 80:
        score += 20
    elif blur > 30:
        score += 10
    # Exposure (0-30 pts)
    score += int(exposure * 30)
    # Noise (0-20 pts)
    score += int(noise * 20)
    # Resolution (0-10 pts)
    mp = pixels / 1_000_000
    if mp > 8:
        score += 10
    elif mp > 3:
        score += 7
    elif mp > 1:
        score += 4

    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    if score >= 30:
        return "D"
    return "F"


def score(path: Path) -> Optional[QualityResult]:
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(path))
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        blur = _blur_score(gray)
        exposure = _exposure_score(gray)
        noise = _noise_score(gray)
        px = w * h
        grade = _grade(blur, exposure, noise, px)
        return QualityResult(blur, exposure, noise, px, grade)
    except Exception:
        return None


def score_entry(entry: "FileEntry") -> None:
    """Populate quality fields on a FileEntry in-place."""
    if entry.file_type != "image":
        return
    result = score(entry.path)
    if result:
        entry.quality_grade = result.grade
        entry.quality_blur = result.blur_score
        entry.quality_exposure = result.exposure_score


def score_all(entries: list["FileEntry"], progress_cb=None) -> None:
    total = len(entries)
    for i, e in enumerate(entries):
        score_entry(e)
        if progress_cb:
            progress_cb(i + 1, total)
