"""
ffmpeg-based video tools: compress, convert, trim, audio extract, GIF, video sheet.
ffmpeg is auto-detected from PATH and common install locations.
All functions raise RuntimeError if ffmpeg is not found.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


_FFMPEG_CACHE: Optional[str] = None

_COMMON_PATHS = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
]


def find_ffmpeg() -> Optional[str]:
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE
    # PATH first
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG_CACHE = found
        return found
    # Common locations
    for p in _COMMON_PATHS:
        if Path(p).is_file():
            _FFMPEG_CACHE = p
            return p
    return None


def _ff(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError(
            "ffmpeg not found. Download from https://ffmpeg.org/download.html "
            "and add to PATH (or place at C:\\ffmpeg\\bin\\ffmpeg.exe)."
        )
    cmd = [ff] + args
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def compress_video(
    src: Path,
    dest: Optional[Path] = None,
    crf: int = 23,
    resolution: Optional[str] = None,
) -> Path:
    """Re-encode video with H.264/AAC at given CRF quality (18=high, 28=low)."""
    out = dest or src.with_stem(src.stem + "_compressed").with_suffix(".mp4")
    vf = f"scale={resolution}" if resolution else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    result = _ff([
        "-y", "-i", str(src),
        "-vcodec", "libx264", "-crf", str(crf),
        "-preset", "fast",
        "-vf", vf,
        "-acodec", "aac", "-b:a", "128k",
        str(out),
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg compress failed: {result.stderr.decode(errors='replace')[-500:]}")
    return out


def convert_to_mp4(src: Path, dest: Optional[Path] = None) -> Path:
    """Convert any video to MP4 (H.264/AAC)."""
    out = dest or src.with_suffix(".mp4")
    result = _ff([
        "-y", "-i", str(src),
        "-vcodec", "libx264", "-crf", "22", "-preset", "fast",
        "-acodec", "aac", "-b:a", "128k",
        str(out),
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg convert failed: {result.stderr.decode(errors='replace')[-500:]}")
    return out


def trim_video(src: Path, start_s: float, end_s: float,
               dest: Optional[Path] = None) -> Path:
    """Cut video to [start_s, end_s] range."""
    out = dest or src.with_stem(src.stem + f"_trim_{int(start_s)}-{int(end_s)}")
    result = _ff([
        "-y", "-i", str(src),
        "-ss", str(start_s), "-to", str(end_s),
        "-c", "copy",
        str(out),
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg trim failed: {result.stderr.decode(errors='replace')[-500:]}")
    return out


def extract_audio(src: Path, dest: Optional[Path] = None,
                  fmt: str = "mp3") -> Path:
    """Extract audio track from video."""
    codec_map = {"mp3": "libmp3lame", "aac": "aac", "wav": "pcm_s16le",
                 "flac": "flac", "ogg": "libvorbis"}
    codec = codec_map.get(fmt.lower(), "libmp3lame")
    out = dest or src.with_suffix(f".{fmt}")
    result = _ff([
        "-y", "-i", str(src),
        "-vn", "-acodec", codec,
        str(out),
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {result.stderr.decode(errors='replace')[-500:]}")
    return out


def video_to_gif(src: Path, dest: Optional[Path] = None,
                 fps: int = 10, scale: int = 480) -> Path:
    """Convert video to animated GIF using palette for quality."""
    out = dest or src.with_suffix(".gif")
    palette = src.with_suffix(".palette.png")
    try:
        # Pass 1: generate palette
        _ff([
            "-y", "-i", str(src),
            "-vf", f"fps={fps},scale={scale}:-1:flags=lanczos,palettegen",
            str(palette),
        ])
        # Pass 2: render GIF
        result = _ff([
            "-y", "-i", str(src), "-i", str(palette),
            "-filter_complex",
            f"fps={fps},scale={scale}:-1:flags=lanczos[x];[x][1:v]paletteuse",
            str(out),
        ])
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg GIF failed: {result.stderr.decode(errors='replace')[-500:]}")
    finally:
        if palette.exists():
            palette.unlink()
    return out


def make_video_sheet(
    src: Path,
    dest: Optional[Path] = None,
    cols: int = 4,
    rows: int = 3,
) -> Path:
    """Generate a thumbnail grid image from N frames of a video."""
    from PIL import Image
    import tempfile, os
    n_frames = cols * rows
    out = dest or src.with_suffix(".sheet.jpg")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract n_frames evenly spaced frames
        result = _ff([
            "-y", "-i", str(src),
            "-vf", f"select=not(mod(n\\,max(1\\,trunc(n/{n_frames}))))",
            "-vframes", str(n_frames),
            "-vsync", "0",
            f"{tmpdir}/frame%03d.jpg",
        ], timeout=60)
        frames = sorted(Path(tmpdir).glob("frame*.jpg"))[:n_frames]
        if not frames:
            raise RuntimeError("No frames extracted for video sheet")

        thumbs = []
        for f in frames:
            img = Image.open(f).convert("RGB")
            img.thumbnail((320, 240))
            thumbs.append(img)

        tw, th = thumbs[0].size if thumbs else (320, 240)
        sheet = Image.new("RGB", (tw * cols, th * rows), color=(20, 20, 30))
        for idx, thumb in enumerate(thumbs):
            r, c = divmod(idx, cols)
            sheet.paste(thumb, (c * tw, r * th))
        sheet.save(out, format="JPEG", quality=85)
    return out


def strip_video_metadata(src: Path, dest: Optional[Path] = None) -> Path:
    """Remove all metadata from a video file."""
    out = dest or src.with_stem(src.stem + "_clean")
    result = _ff([
        "-y", "-i", str(src),
        "-map_metadata", "-1",
        "-c", "copy",
        str(out),
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg metadata strip failed")
    return out


def detect_scene_cuts(src: Path, threshold: float = 0.4) -> list[float]:
    """Return list of timestamps (seconds) where scene cuts occur."""
    result = _ff([
        "-i", str(src),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ], timeout=120)
    times = []
    for line in result.stderr.decode(errors="replace").splitlines():
        if "pts_time:" in line:
            try:
                t = float(line.split("pts_time:")[1].split()[0])
                times.append(t)
            except (ValueError, IndexError):
                pass
    return times


def merge_videos(srcs: list[Path], dest: Path) -> Path:
    """Concatenate video files using ffmpeg concat demuxer."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for s in srcs:
            f.write(f"file '{s.resolve()}'\n")
        flist = f.name
    try:
        result = _ff([
            "-y", "-f", "concat", "-safe", "0",
            "-i", flist, "-c", "copy",
            str(dest),
        ])
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg merge failed: {result.stderr.decode(errors='replace')[-500:]}")
    finally:
        Path(flist).unlink(missing_ok=True)
    return dest
