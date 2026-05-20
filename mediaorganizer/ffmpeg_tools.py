"""FFmpeg-based video processing tools."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

_KNOWN_PATHS = [
    r'C:\ffmpeg\ffmpeg-2026-01-14-git-6c878f8b82-full_build\ffmpeg-2026-01-14-git-6c878f8b82-full_build\bin\ffmpeg.exe',
    r'C:\ffmpeg\bin\ffmpeg.exe',
    r'C:\ffmpeg\ffmpeg.exe',
    r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
    r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
    '/usr/bin/ffmpeg',
    '/usr/local/bin/ffmpeg',
    '/opt/homebrew/bin/ffmpeg',
]


def find_ffmpeg() -> Optional[str]:
    found = shutil.which('ffmpeg')
    if found:
        return found
    for p in _KNOWN_PATHS:
        if os.path.isfile(p):
            return p
    return None


FFMPEG: Optional[str] = find_ffmpeg()


def is_available() -> bool:
    return FFMPEG is not None


def compress_video(
    src: Path,
    dest: Optional[Path] = None,
    crf: int = 23,
    preset: str = 'medium',
) -> Path:
    """Re-encode video to H.264/AAC MP4. Lower CRF = higher quality (18-28 typical)."""
    if not FFMPEG:
        raise RuntimeError('ffmpeg not found. Download free at https://ffmpeg.org/')
    if dest is None:
        dest = src.with_stem(src.stem + '_compressed').with_suffix('.mp4')
    cmd = [FFMPEG, '-i', str(src),
           '-c:v', 'libx264', '-crf', str(crf), '-preset', preset,
           '-c:a', 'aac', '-b:a', '128k',
           '-movflags', '+faststart', '-y', str(dest)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'ffmpeg error:\n{result.stderr[-2000:]}')
    return dest


def convert_to_mp4(src: Path, dest: Optional[Path] = None) -> Path:
    """Convert any video to H.264/AAC MP4."""
    if not FFMPEG:
        raise RuntimeError('ffmpeg not found. Download free at https://ffmpeg.org/')
    if dest is None:
        dest = src.with_suffix('.mp4')
        if dest == src:
            dest = src.with_stem(src.stem + '_converted').with_suffix('.mp4')
    cmd = [FFMPEG, '-i', str(src),
           '-c:v', 'libx264', '-crf', '22',
           '-c:a', 'aac', '-b:a', '128k',
           '-movflags', '+faststart', '-y', str(dest)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'ffmpeg error:\n{result.stderr[-2000:]}')
    return dest


_VIDEO_EXTS = {'.mov', '.avi', '.wmv', '.mkv', '.flv', '.webm', '.m4v', '.3gp', '.ts'}


def batch_convert_to_mp4(
    folder: Path,
    recursive: bool = True,
    extensions: Optional[set] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> list:
    """Convert non-MP4 videos in folder to MP4. Returns (src, dest) pairs."""
    if not FFMPEG:
        raise RuntimeError('ffmpeg not found.')
    exts = extensions or _VIDEO_EXTS
    paths = list(folder.rglob('*') if recursive else folder.iterdir())
    paths = [p for p in paths if p.suffix.lower() in exts]
    results = []
    for i, src in enumerate(paths):
        if progress:
            progress(i, len(paths), src.name)
        try:
            results.append((src, convert_to_mp4(src)))
        except Exception:
            pass
    if progress and paths:
        progress(len(paths), len(paths), 'Done')
    return results


def batch_compress_videos(
    folder: Path,
    crf: int = 23,
    recursive: bool = True,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> list:
    """Compress all videos in folder. Returns (src, dest) pairs."""
    if not FFMPEG:
        raise RuntimeError('ffmpeg not found.')
    all_video = _VIDEO_EXTS | {'.mp4'}
    paths = list(folder.rglob('*') if recursive else folder.iterdir())
    paths = [p for p in paths if p.suffix.lower() in all_video]
    results = []
    for i, src in enumerate(paths):
        if progress:
            progress(i, len(paths), src.name)
        try:
            results.append((src, compress_video(src, crf=crf)))
        except Exception:
            pass
    if progress and paths:
        progress(len(paths), len(paths), 'Done')
    return results
