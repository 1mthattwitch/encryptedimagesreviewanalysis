@echo off
setlocal enabledelayedexpansion
title Media Organizer
cd /d "%~dp0"

echo.
echo  ============================================================
echo    Media Organizer  --  Gallery Vault File Processor
echo  ============================================================
echo.

:: ── Step 1: Find Python ─────────────────────────────────────────────────
echo [1/5] Finding Python...

:: Try 'python' first, then 'py' (Windows Launcher), then common install paths
set PYTHON=

python --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON=python
    goto PYTHON_FOUND
)

py --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON=py
    goto PYTHON_FOUND
)

:: Try common install locations
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "%APPDATA%\Microsoft\WindowsApps\python.exe"
) do (
    if exist %%P (
        set PYTHON=%%~P
        goto PYTHON_FOUND
    )
)

echo.
echo  ERROR: Python could not be found.
echo.
echo  You said you have Python -- it is probably just not on your PATH.
echo  Fix: open Python installer again and tick "Add Python to PATH", OR
echo       search Windows for "Python" and note the install folder, then
echo       add it to System Environment Variables ^> PATH.
echo.
echo  Quick check: open a new Command Prompt and type:  python --version
echo  If that shows a version, close this window and run run.bat again.
echo  If not, try:  py --version
echo.
pause
exit /b 1

:PYTHON_FOUND
"%PYTHON%" --version
echo   Found as: %PYTHON%
echo.

:: ── Step 2: Create venv ─────────────────────────────────────────────────
echo [2/5] Setting up virtual environment...
if not exist ".venv\Scripts\activate.bat" (
    echo   Creating .venv for the first time...
    "%PYTHON%" -m venv .venv
    if !errorlevel! neq 0 (
        echo.
        echo  ERROR: Failed to create virtual environment.
        echo  Try running this in a terminal:  %PYTHON% -m pip install --upgrade pip
        echo.
        pause
        exit /b 1
    )
    echo   .venv created.
) else (
    echo   .venv already exists.
)
call .venv\Scripts\activate.bat
echo   Virtual environment active.
echo.

:: ── Step 3: Auto-update from GitHub ─────────────────────────────────────────
echo [3/5] Checking for updates...
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
echo     "mediaorganizer/antivirus.py",
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

:: ── Step 4: Install dependencies ───────────────────────────────────────────
echo [4/5] Installing / updating dependencies...
pip install --quiet --exists-action i -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo  WARNING: Some packages may have failed. Tool may still work.
)
echo   done.
echo.

:: ── Step 5: Launch GUI ─────────────────────────────────────────────────
echo [5/5] Launching Media Organizer...
echo.
python -m mediaorganizer.gui

if !errorlevel! neq 0 (
    echo.
    echo  ERROR: The GUI failed to start.
    echo  Common fix: pip install Pillow
    echo  Or paste the error above into chat for help.
)

echo.
echo  Deactivating virtual environment...
call .venv\Scripts\deactivate.bat 2>nul
pause
