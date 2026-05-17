"""Ollama-powered image/video description and content categorisation."""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

import requests

from .scanner import FileEntry

CATEGORIES = [
    'People', 'Selfies', 'Landscapes', 'Animals', 'Food',
    'Screenshots', 'Documents', 'Events', 'Architecture', 'Other',
]
DEFAULT_HOST = 'http://localhost:11434'
VISION_MODELS = ['moondream', 'llava', 'bakllava', 'llava-phi3']


class OllamaAnalyzer:
    def __init__(self, host: str = DEFAULT_HOST):
        self.host = host.rstrip('/')
        self._model: Optional[str] = None

    def is_available(self) -> bool:
        try:
            r = requests.get(f'{self.host}/api/tags', timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def _get_model(self) -> Optional[str]:
        if self._model:
            return self._model
        try:
            r = requests.get(f'{self.host}/api/tags', timeout=5)
            available = [m['name'] for m in r.json().get('models', [])]
            for preferred in VISION_MODELS:
                for m in available:
                    if m.startswith(preferred):
                        self._model = m
                        return self._model
        except Exception:
            pass
        return None

    def _encode_image(self, path: Path, max_px: int = 1024) -> Optional[str]:
        try:
            from PIL import Image
            img = Image.open(path).convert('RGB')
            img.thumbnail((max_px, max_px), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=85)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def _video_keyframe_b64(self, path: Path) -> Optional[str]:
        try:
            import cv2
            from PIL import Image
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                return None
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 5))
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            cap.release()
            if not ret:
                return None
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img.thumbnail((1024, 1024), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=85)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def _call(self, prompt: str, image_b64: str) -> Optional[str]:
        model = self._get_model()
        if not model:
            return None
        try:
            payload = {
                'model': model,
                'prompt': prompt,
                'images': [image_b64],
                'stream': False,
            }
            r = requests.post(f'{self.host}/api/generate', json=payload, timeout=90)
            r.raise_for_status()
            return r.json().get('response', '').strip()
        except Exception:
            return None

    def _get_image_b64(self, entry: FileEntry) -> Optional[str]:
        if entry.file_type == 'image':
            return self._encode_image(entry.path)
        if entry.file_type == 'video':
            return self._video_keyframe_b64(entry.path)
        return None

    def describe(self, entry: FileEntry) -> Optional[str]:
        b64 = self._get_image_b64(entry)
        if not b64:
            return None
        prompt = (
            'Describe this image in 5 to 10 words suitable as a filename. '
            'Be specific about the content, setting, and mood. '
            'Return ONLY the description, no punctuation at the end.'
        )
        return self._call(prompt, b64)

    def categorize(self, entry: FileEntry) -> Optional[str]:
        b64 = self._get_image_b64(entry)
        if not b64:
            return None
        prompt = (
            f'Which single category best describes this image? '
            f'Choose exactly one from: {", ".join(CATEGORIES)}. '
            f'Return ONLY the category name, nothing else.'
        )
        result = self._call(prompt, b64)
        if result:
            for cat in CATEGORIES:
                if cat.lower() in result.lower():
                    return cat
        return 'Other'


def _heuristic_name(entry: FileEntry) -> str:
    if entry.date:
        return entry.date.strftime('%Y-%m-%d_%H%M%S')
    return entry.path.stem


def _sanitize(text: str, max_words: int = 8) -> str:
    import re
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^\w\s-]', '', text)
    words = text.split()[:max_words]
    return '_'.join(w.lower() for w in words if w) or 'file'


def analyze_entries(
    entries: list[FileEntry],
    ai: OllamaAnalyzer,
    need_category: bool = False,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> None:
    """Fill ai_description, ai_category, and proposed_name on each entry in-place."""
    online = ai.is_available()
    for i, entry in enumerate(entries):
        if progress_cb:
            progress_cb(i, len(entries), entry.path.name)
        if entry.file_type in ('image', 'video'):
            if online:
                desc = ai.describe(entry)
                if desc:
                    entry.ai_description = desc
                    entry.proposed_name = _sanitize(desc)
                else:
                    entry.proposed_name = _heuristic_name(entry)
            else:
                entry.proposed_name = _heuristic_name(entry)
            if need_category and online:
                cat = ai.categorize(entry)
                entry.ai_category = cat or 'Other'
        else:
            entry.proposed_name = _heuristic_name(entry)
