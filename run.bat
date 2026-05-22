@echo off
setlocal enabledelayedexpansion
title Media Organizer

echo.
echo  ============================================================
echo   Media Organizer — Offline Media Scanner ^& AI Renamer
echo  ============================================================
echo.

:: ── 1. Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Download from: https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during install.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Python: %PY_VER%

:: ── 2. Check Git + pull latest ───────────────────────────────────────────────
git --version >nul 2>&1
if errorlevel 1 (
    echo  [WARN] Git not found — skipping auto-update.
    goto :install_deps
)

echo  Pulling latest updates...
git fetch origin claude/decrypt-gallery-vault-POpHP --quiet 2>nul
if not errorlevel 1 (
    git merge origin/claude/decrypt-gallery-vault-POpHP --ff-only --quiet 2>nul
    if not errorlevel 1 (
        echo  Up to date.
    ) else (
        echo  [WARN] Could not auto-merge — continuing with local version.
    )
) else (
    echo  [WARN] Could not reach GitHub — continuing offline.
)

:: ── 3. Install / update Python deps ─────────────────────────────────────────
:install_deps
echo  Installing / checking dependencies...
python -m pip install -r requirements.txt --quiet --exists-action i
if errorlevel 1 (
    echo  [ERROR] pip install failed. Check internet connection or run manually:
    echo    pip install -r requirements.txt
    pause & exit /b 1
)
echo  Dependencies OK.
echo.

:: ── 4. Check ffmpeg ──────────────────────────────────────────────────────────
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    if exist "C:\ffmpeg\bin\ffmpeg.exe" (
        echo  ffmpeg found at C:\ffmpeg\bin\ffmpeg.exe
    ) else (
        echo  [WARN] ffmpeg not found. Video tools will be limited.
        echo  Download: https://ffmpeg.org/download.html
        echo  Extract and add bin\ folder to PATH, or place at C:\ffmpeg\bin\
        echo.
    )
) else (
    echo  ffmpeg: OK
)

:: ── 5. Check Ollama ──────────────────────────────────────────────────────────
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Ollama not running — AI descriptions will use heuristics.
    echo  To enable AI: https://ollama.ai  then: ollama pull moondream
) else (
    echo  Ollama: running
)
echo.

:: ── 6. Launch GUI ─────────────────────────────────────────────────────────────
echo  Launching Media Organizer GUI...
python -m mediaorganizer.gui
if errorlevel 1 (
    echo.
    echo  [ERROR] The app crashed. Error details above.
    pause
)
