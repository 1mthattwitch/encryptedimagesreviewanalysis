"""
AI analysis using local Ollama (offline, no API key).
Provides short filename descriptions and content category detection.
Falls back to heuristics when Ollama is unavailable.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry

DEFAULT_HOST = "http://localhost:11434"

CATEGORIES = [
    "People", "Selfies", "Landscapes", "Animals", "Food",
    "Screenshots", "Documents", "Events", "Architecture",
    "Nature", "Art", "Travel", "Sports", "Vehicles", "Other",
]


def is_available(host: str = DEFAULT_HOST) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def list_models(host: str = DEFAULT_HOST) -> list[str]:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return []


def _best_vision_model(host: str) -> Optional[str]:
    available = list_models(host)
    candidates = ["moondream", "moondream:latest", "llava", "llava:latest",
                  "llava:7b", "llava:13b", "bakllava", "bakllava:latest"]
    avail_lower = {m.lower(): m for m in available}
    for c in candidates:
        if c in avail_lower:
            return avail_lower[c]
    for name in available:
        if any(k in name.lower() for k in ("llava", "moondream", "vision", "bakllava")):
            return name
    return None


def _post(url: str, payload: dict, timeout: int = 90) -> Optional[dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _encode_image(path: Path, max_px: int = 1024) -> Optional[str]:
    try:
        from PIL import Image
        import io
        img = Image.open(path).convert("RGB")
        img.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _video_keyframe_b64(path: Path) -> Optional[str]:
    try:
        import cv2
        import numpy as np
        from PIL import Image
        import io
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(int(total * 0.1), 30)))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def describe_image(image_b64: str, host: str = DEFAULT_HOST,
                   model: Optional[str] = None) -> Optional[str]:
    if model is None:
        model = _best_vision_model(host)
    if model is None:
        return None
    payload = {
        "model": model,
        "prompt": (
            "Describe this image in 5 to 10 words suitable as a filename. "
            "Be specific about what you see. "
            "Return ONLY the description, no punctuation, no extra text."
        ),
        "images": [image_b64],
        "stream": False,
    }
    result = _post(f"{host}/api/generate", payload)
    if not result:
        return None
    line = result.get("response", "").strip().splitlines()[0].strip(" .,:;\"'")
    return line if len(line) > 3 else None


def categorize_image(image_b64: str, host: str = DEFAULT_HOST,
                     model: Optional[str] = None) -> Optional[str]:
    if model is None:
        model = _best_vision_model(host)
    if model is None:
        return None
    cats = ", ".join(CATEGORIES)
    payload = {
        "model": model,
        "prompt": (
            f"Classify this image into exactly one of these categories: {cats}. "
            "Reply with ONLY the category name, nothing else."
        ),
        "images": [image_b64],
        "stream": False,
    }
    result = _post(f"{host}/api/generate", payload)
    if not result:
        return None
    raw = result.get("response", "").strip().splitlines()[0].strip()
    # Match to known category
    for cat in CATEGORIES:
        if cat.lower() in raw.lower():
            return cat
    return "Other"


# ── Heuristic fallbacks ──────────────────────────────────────────────────────

def _heuristic_description(entry: "FileEntry") -> str:
    """Build a description from EXIF/filename when AI is unavailable."""
    parts = []
    if entry.camera:
        parts.append(entry.camera.split()[-1])  # last word of model
    if entry.date:
        parts.append(entry.date.strftime("%Y-%m-%d"))
    if entry.width and entry.height:
        parts.append(f"{entry.width}x{entry.height}")
    if entry.duration_s:
        parts.append(f"{entry.duration_s:.0f}s")
    if not parts:
        stem = entry.path.stem
        stem = re.sub(r"[_\-]+", " ", stem).strip()
        parts.append(stem[:40] if stem else "unnamed")
    return " ".join(parts)


def _heuristic_category(entry: "FileEntry") -> str:
    name_lower = entry.path.name.lower()
    # Common patterns
    if re.search(r"img[-_]\d{8}[-_]wa\d+", name_lower):
        return "People"          # WhatsApp photo
    if re.search(r"screenshot", name_lower):
        return "Screenshots"
    if re.search(r"vid[-_]|video", name_lower):
        return "Other"
    if entry.width and entry.height:
        # Likely a selfie if tall portrait
        ratio = entry.height / entry.width if entry.width else 1
        if ratio > 1.4:
            return "Selfies"
    return "Other"


# ── Public API ───────────────────────────────────────────────────────────────

def analyze_entry(
    entry: "FileEntry",
    host: str = DEFAULT_HOST,
    use_ai: bool = True,
) -> None:
    """Populate entry.ai_description, entry.ai_category, entry.proposed_name in-place."""
    b64 = None
    if use_ai and entry.file_type == "image":
        b64 = _encode_image(entry.path)
    elif use_ai and entry.file_type == "video":
        b64 = _video_keyframe_b64(entry.path)

    if b64 and use_ai and is_available(host):
        entry.ai_description = describe_image(b64, host)
        entry.ai_category = categorize_image(b64, host)

    if not entry.ai_description:
        entry.ai_description = _heuristic_description(entry)
    if not entry.ai_category:
        entry.ai_category = _heuristic_category(entry)

    # Propose new name
    safe = _safe_name(entry.ai_description)
    ext = entry.path.suffix.lower()
    entry.proposed_name = f"{safe}{ext}"


def _safe_name(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s\-]", " ", text)
    text = re.sub(r"\s+", "_", text.strip())
    text = text.strip("_-")[:80]
    return text or "unnamed"


def analyze_all(
    entries: list["FileEntry"],
    host: str = DEFAULT_HOST,
    use_ai: bool = True,
    progress_cb=None,
) -> None:
    """Analyze all entries, calling optional progress_cb(i, total) after each."""
    total = len(entries)
    for i, entry in enumerate(entries):
        if entry.file_type in ("image", "video"):
            analyze_entry(entry, host=host, use_ai=use_ai)
        if progress_cb:
            progress_cb(i + 1, total)
