#!/usr/bin/env python3
"""Self-test for Media Organizer. Run from inside the .venv."""
import sys
import os
import shutil
import importlib
import importlib.util
import urllib.request

_results = []

def record(status, label, detail=""):
    _results.append((status, label, detail))
    _COLORS = {"PASS": "\033[32m", "WARN": "\033[33m", "FAIL": "\033[31m"}
    col   = _COLORS.get(status, "")
    reset = "\033[0m" if col else ""
    pad   = " " * (4 - len(status))
    detail_str = f"\n          {detail}" if detail else ""
    print(f"  {col}{status}{reset}{pad} {label}{detail_str}")

def check_pkg(import_name, display, pip_name=None, required=True):
    try:
        mod = importlib.import_module(import_name)
        ver = getattr(mod, "__version__", "?")
        record("PASS", f"Package: {display}", f"v{ver}")
    except ImportError:
        if required:
            fix = f"pip install {pip_name or display}"
            record("FAIL", f"Package: {display}", f"Not installed — {fix}")
        else:
            record("WARN", f"Package: {display} (optional)", "Not installed")

print()
print("  " + "=" * 60)
print("    Media Organizer  --  self-test")
print("  " + "=" * 60)
print()

# ── Virtual environment ───────────────────────────────────────────────────────
print("[ Virtual environment ]")
if sys.prefix != sys.base_prefix:
    record("PASS", "Running inside .venv", sys.prefix)
else:
    record("FAIL", "Not running inside .venv",
           "Run via run.bat, or manually:\n"
           "          .venv\\Scripts\\activate  (Windows)\n"
           "          source .venv/bin/activate  (Linux/Mac)\n"
           "          then: python selftest.py")
print()

# ── Required packages ─────────────────────────────────────────────────────────
print("[ Python & required packages ]")
record("PASS", "Python version", sys.version.split()[0])

REQUIRED = [
    ("PIL",         "Pillow",       "Pillow"),
    ("pillow_heif", "pillow-heif",  "pillow-heif"),
    ("fitz",        "PyMuPDF",      "PyMuPDF"),
    ("docx",        "python-docx",  "python-docx"),
    ("odf",         "odfpy",        "odfpy"),
    ("imagehash",   "imagehash",    "imagehash"),
    ("cv2",         "opencv",       "opencv-python-headless"),
    ("numpy",       "numpy",        "numpy"),
    ("requests",    "requests",     "requests"),
]
for imp, disp, pip in REQUIRED:
    check_pkg(imp, disp, pip, required=True)
print()

# ── Optional packages ─────────────────────────────────────────────────────────
print("[ Optional packages ]")
OPTIONAL = [
    ("watchdog",    "watchdog",       "watchdog"),
    ("pytesseract", "pytesseract",    "pytesseract"),
    ("whisper",     "openai-whisper", "openai-whisper"),
    ("rembg",       "rembg",          "rembg"),
    ("folium",      "folium",         "folium"),
]
for imp, disp, pip in OPTIONAL:
    check_pkg(imp, disp, pip, required=False)
print()

# ── mediaorganizer modules ────────────────────────────────────────────────────
print("[ mediaorganizer modules ]")
_has_tkinter = importlib.util.find_spec("tkinter") is not None

MODULES = [
    ("mediaorganizer",                False),
    ("mediaorganizer.scanner",        False),
    ("mediaorganizer.health",         False),
    ("mediaorganizer.duplicates",     False),
    ("mediaorganizer.analyzer",       False),
    ("mediaorganizer.organizer",      False),
    ("mediaorganizer.reporter",       False),
    ("mediaorganizer.exporter",       False),
    ("mediaorganizer.antivirus",      False),
    ("mediaorganizer.converter",      False),
    ("mediaorganizer.ffmpeg_tools",   False),
    ("mediaorganizer.quality",        False),
    ("mediaorganizer.faces",          False),
    ("mediaorganizer.ocr",            False),
    ("mediaorganizer.events",         False),
    ("mediaorganizer.watcher",        False),
    ("mediaorganizer.transcript",     False),
    ("mediaorganizer.contact_sheet",  False),
    ("mediaorganizer.watermark",      False),
    ("mediaorganizer.repair",         False),
    ("mediaorganizer.mapview",        False),
    ("mediaorganizer.cli",            False),
    ("mediaorganizer.dupe_finder",    True),   # needs tkinter
    ("mediaorganizer.gui",            True),   # needs tkinter + display
]
for mod, needs_tk in MODULES:
    if needs_tk and not _has_tkinter:
        record("WARN", f"Import: {mod}", "tkinter not available in this environment (OK on Windows)")
        continue
    try:
        importlib.import_module(mod)
        record("PASS", f"Import: {mod}")
    except ImportError as e:
        record("FAIL", f"Import: {mod}", str(e))
    except Exception as e:
        record("WARN", f"Import: {mod}", str(e))
print()

# ── External tools ────────────────────────────────────────────────────────────
print("[ External tools ]")
ffmpeg = shutil.which("ffmpeg")
if ffmpeg:
    record("PASS", "ffmpeg", ffmpeg)
else:
    record("WARN", "ffmpeg not found",
           "Video tools disabled -- https://ffmpeg.org/download.html")

tesseract = shutil.which("tesseract")
if tesseract:
    record("PASS", "Tesseract", tesseract)
else:
    record("WARN", "Tesseract not found",
           "OCR disabled -- https://tesseract-ocr.github.io")

try:
    urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
    record("PASS", "Ollama", "running at localhost:11434")
except Exception:
    record("WARN", "Ollama not running",
           "AI descriptions will use heuristics -- https://ollama.ai")
print()

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(1 for s, _, _ in _results if s == "PASS")
warned = sum(1 for s, _, _ in _results if s == "WARN")
failed = sum(1 for s, _, _ in _results if s == "FAIL")
total  = len(_results)

print("  " + "=" * 60)
print("  Summary")
print(f"  {passed} passed  {warned} warnings  {failed} failed  (of {total} checks)")
print()
if failed:
    print("  Some critical checks failed.")
    print("  Fix the FAIL items above, then re-run: python selftest.py")
print("  " + "=" * 60)
print()

sys.exit(1 if failed else 0)
