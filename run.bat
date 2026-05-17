@echo off
setlocal enabledelayedexpansion
title Media Organizer
cd /d "%~dp0"

echo.
echo  ============================================================
echo    Media Organizer  --  Gallery Vault File Processor
echo  ============================================================
echo.

:: ── Step 1: Check Python ────────────────────────────────────────────────────
echo [1/4] Checking Python...
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo  ERROR: Python is not installed or not on PATH.
    echo  Download it from https://www.python.org/downloads/
    echo  (Make sure to tick "Add Python to PATH" during install)
    echo.
    pause
    exit /b 1
)
python --version
echo.

:: ── Step 2: Auto-update from GitHub ─────────────────────────────────────────
echo [2/4] Checking for updates...
(
echo import urllib.request, os, sys
echo BRANCH = "claude/decrypt-gallery-vault-POpHP"
echo BASE = "https://raw.githubusercontent.com/1mthattwitch/encryptedimagesreviewanalysis/" + BRANCH + "/"
echo FILES = [
echo     "mediaorganizer/__init__.py",
echo     "mediaorganizer/scanner.py",
echo     "mediaorganizer/health.py",
echo     "mediaorganizer/duplicates.py",
echo     "mediaorganizer/analyzer.py",
echo     "mediaorganizer/organizer.py",
echo     "mediaorganizer/reporter.py",
echo     "mediaorganizer/exporter.py",
echo     "mediaorganizer/cli.py",
echo     "mediaorganizer/gui.py",
echo     "requirements.txt",
echo ]
echo ok = 0
echo for f in FILES:
echo     os.makedirs^(os.path.dirname^(f^) or ".", exist_ok=True^)
echo     try:
echo         urllib.request.urlretrieve^(BASE + f, f^)
echo         print^("  + " + f^)
echo         ok += 1
echo     except Exception as e:
echo         print^("  ! " + f + " -- " + str^(e^)^)
echo if ok == 0:
echo     print^("  No network -- running with existing files."^)
echo else:
echo     print^("  Updated " + str^(ok^) + " file(s^)."^)
) > _update.py
python _update.py
del _update.py
echo.

:: ── Step 3: Install dependencies ────────────────────────────────────────────
echo [3/4] Installing / checking dependencies...
pip install --quiet --exists-action i Pillow PyMuPDF python-docx imagehash opencv-python-headless numpy requests odfpy
if !errorlevel! neq 0 (
    echo.
    echo  WARNING: Some packages may have failed to install.
    echo  The tool will still work for basic features.
)
echo   done.
echo.

:: ── Step 4: Launch GUI ──────────────────────────────────────────────────────
echo [4/4] Launching Media Organizer...
echo.
python -m mediaorganizer.gui

if !errorlevel! neq 0 (
    echo.
    echo  ERROR: The GUI failed to start. See the message above.
    echo  Common fix: pip install Pillow
)

echo.
pause
