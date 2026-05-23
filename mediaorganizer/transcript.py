"""
Video/audio transcription using Whisper (offline, optional dep).
Saves .txt sidecar files next to the source video.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


def is_available() -> bool:
    try:
        import whisper  # noqa
        return True
    except ImportError:
        return False


def transcribe(path: Path, model_name: str = "tiny") -> str:
    """
    Transcribe audio/video to text using Whisper.
    model_name: 'tiny' (~39 MB), 'base' (~74 MB), 'small' (~244 MB)
    Returns transcribed text, or raises ImportError if whisper not installed.
    """
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "openai-whisper not installed. Run: pip install openai-whisper\n"
            "Note: requires ffmpeg on PATH."
        )
    model = whisper.load_model(model_name)
    result = model.transcribe(str(path))
    return result.get("text", "").strip()


def transcribe_and_save(path: Path, model_name: str = "tiny") -> Optional[Path]:
    """Transcribe and save .txt sidecar next to video. Returns sidecar path or None."""
    try:
        text = transcribe(path, model_name)
        if not text:
            return None
        sidecar = path.with_suffix(".transcript.txt")
        sidecar.write_text(text, encoding="utf-8")
        return sidecar
    except ImportError:
        raise
    except Exception:
        return None


def transcribe_entry(entry: "FileEntry", model_name: str = "tiny") -> None:
    if entry.file_type not in ("video", "audio"):
        return
    try:
        text = transcribe(entry.path, model_name)
        entry.transcript = text or None
    except ImportError:
        raise
    except Exception:
        entry.transcript = None


def transcribe_all(
    entries: list["FileEntry"],
    model_name: str = "tiny",
    progress_cb=None,
) -> None:
    media = [e for e in entries if e.file_type in ("video", "audio")]
    total = len(media)
    for i, e in enumerate(media):
        transcribe_entry(e, model_name)
        if progress_cb:
            progress_cb(i + 1, total)
