@echo off
setlocal enabledelayedexpansion
title Media Organizer
cd /d "%~dp0"

echo.
echo  ============================================================
echo    Media Organizer  --  Gallery Vault File Processor
echo  ============================================================
echo.
echo  Do you need to export files from Gallery Vault first?
echo.
echo    [1]  Yes -- help me get files off my phone first
echo    [2]  No  -- I already have the files, launch the tool
echo.
set /p STARTWITH="  Your choice (1 or 2): "
echo.

if "%STARTWITH%"=="1" goto EXPORT_MENU
if "%STARTWITH%"=="2" goto SETUP
echo  Invalid choice. Press any key and run again.
pause
exit /b 1


:: ============================================================
:EXPORT_MENU
echo  ============================================================
echo    Gallery Vault Export
echo    How is your phone connected?
echo  ============================================================
echo.
echo    [1]  In-app export  (easier -- no extra apps needed)
echo    [2]  ADB pull       (faster -- needs USB Debugging ON)
echo.
set /p CHOICE="  Your choice (1 or 2): "
echo.

if "%CHOICE%"=="1" goto IN_APP
if "%CHOICE%"=="2" goto ADB_PULL
echo  Invalid choice. Press any key and run again.
pause
exit /b 1


:: ============================================================
:IN_APP
echo  ============================================================
echo    Method 1: Gallery Vault In-App Export
echo  ============================================================
echo.
echo  Follow these steps on your PHONE:
echo.
echo    1. Open the Gallery Vault app.
echo.
echo    2. Tap the three-dot menu (top-right corner).
echo       Select "Restore" or "Export to Gallery".
echo.
echo    3. Select all files (long-press, then Select All).
echo       Tap "Restore" or "Move to Gallery".
echo.
echo    4. The files will now appear in your phone's normal
echo       gallery / DCIM / Downloads folder.
echo.
echo  Now connect your phone to the PC:
echo.
echo    5. Plug in USB cable.
echo       When prompted on your phone, choose "File Transfer"
echo       (also called MTP or USB for file transfer).
echo.
echo    6. Open File Explorer on your PC.
echo       Navigate to:  This PC > [Your Phone] > Internal Storage
echo.
echo    7. Find your exported photos/videos (usually in DCIM,
echo       Pictures, or Downloads folder).
echo.
echo    8. Copy everything into the folder below:
echo.
if not exist "GalleryVaultExport" mkdir GalleryVaultExport
echo         %~dp0GalleryVaultExport\
echo.
echo  ============================================================
echo  When you have finished copying, press any key to continue...
pause >nul
echo.
echo  Opening the export folder in Explorer...
explorer "%~dp0GalleryVaultExport"
echo.
goto SETUP


:: ============================================================
:ADB_PULL
echo  ============================================================
echo    Method 2: ADB Pull (USB Debugging)
echo  ============================================================
echo.

adb --version >nul 2>&1
if !errorlevel! neq 0 (
    echo  ERROR: ADB is not installed or not on PATH.
    echo.
    echo  To install ADB:
    echo    1. Download Platform Tools from:
    echo       https://developer.android.com/tools/releases/platform-tools
    echo    2. Extract the zip (e.g. to C:\platform-tools^)
    echo    3. Add that folder to your Windows PATH, OR
    echo       place adb.exe next to this bat file and run again.
    echo.
    pause
    exit /b 1
)
adb --version
echo.

echo  Checking for connected device...
for /f "skip=1 tokens=1" %%D in ('adb devices') do (
    if not "%%D"=="" set DEVICE=%%D
)
if not defined DEVICE (
    echo.
    echo  No device found. Please:
    echo    1. Enable Developer Options on your phone:
    echo       Settings > About Phone > tap Build Number 7 times
    echo    2. Enable USB Debugging:
    echo       Settings > Developer Options > USB Debugging = ON
    echo    3. Connect USB cable and select "File Transfer" on phone
    echo    4. Accept the "Allow USB debugging?" prompt on your phone
    echo    5. Run this script again
    echo.
    pause
    exit /b 1
)
echo  Device connected: !DEVICE!
echo.

echo  Common Gallery Vault storage paths:
echo.
echo    [1]  /sdcard/.GalleryVault          (default, hidden)
echo    [2]  /sdcard/GalleryVault           (older versions)
echo    [3]  /sdcard/Pictures/.nomedia      (some variants)
echo    [4]  /sdcard/Android/data/com.nomad14.addvault/files
echo    [5]  Enter a custom path
echo.
set /p PATHCHOICE="  Choose path (1-5): "

if "%PATHCHOICE%"=="1" set SRCPATH=/sdcard/.GalleryVault
if "%PATHCHOICE%"=="2" set SRCPATH=/sdcard/GalleryVault
if "%PATHCHOICE%"=="3" set SRCPATH=/sdcard/Pictures/.nomedia
if "%PATHCHOICE%"=="4" set SRCPATH=/sdcard/Android/data/com.nomad14.addvault/files
if "%PATHCHOICE%"=="5" (
    set /p SRCPATH="  Enter the full path on your phone: "
)
if not defined SRCPATH (
    echo  Invalid choice.
    pause
    exit /b 1
)
echo.
echo  Source path: !SRCPATH!
if not exist "GalleryVaultExport" mkdir GalleryVaultExport
echo  Destination: %~dp0GalleryVaultExport\
echo.
echo  Pulling files... (this may take a while for large collections)
echo.
adb pull "!SRCPATH!" "%~dp0GalleryVaultExport\"

if !errorlevel! equ 0 (
    echo.
    echo  Transfer complete!
    explorer "%~dp0GalleryVaultExport"
) else (
    echo.
    echo  ADB pull encountered errors. Files may have transferred
    echo  partially. Check %~dp0GalleryVaultExport\
    echo.
    echo  If you see a permissions error, your files may be
    echo  encrypted in-app. Run again and use Method 1 instead.
    explorer "%~dp0GalleryVaultExport"
)
echo.


:: ============================================================
:SETUP
echo  ============================================================
echo    Setting up Media Organizer
echo  ============================================================
echo.

:: --- 1. Find Python -------------------------------------------------------
echo [1/4] Finding Python...

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

for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "C:\Python314\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "%APPDATA%\Microsoft\WindowsApps\python.exe"
) do (
    if exist %%P (
        set PYTHON=%%~P
        goto PYTHON_FOUND
    )
)

echo.
echo  ERROR: Python could not be found.
echo  Download from: https://www.python.org/downloads/
echo  Make sure to check "Add Python to PATH" during install.
echo  Then close this window and run run.bat again.
echo.
pause
exit /b 1

:PYTHON_FOUND
"%PYTHON%" --version
echo   Using: %PYTHON%
echo.

:: --- 2. Virtual environment -----------------------------------------------
echo [2/4] Setting up virtual environment...
if not exist ".venv\Scripts\activate.bat" (
    echo   Creating .venv for the first time...
    "%PYTHON%" -m venv .venv
    if !errorlevel! neq 0 (
        echo.
        echo  ERROR: Failed to create virtual environment.
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

:: --- 3. Auto-update from GitHub -------------------------------------------
echo [3/4] Checking for updates...
(
echo import urllib.request, os
echo BRANCH = "main"
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
echo     "mediaorganizer/converter.py",
echo     "mediaorganizer/ffmpeg_tools.py",
echo     "mediaorganizer/dupe_finder.py",
echo     "mediaorganizer/quality.py",
echo     "mediaorganizer/faces.py",
echo     "mediaorganizer/ocr.py",
echo     "mediaorganizer/events.py",
echo     "mediaorganizer/watcher.py",
echo     "mediaorganizer/transcript.py",
echo     "mediaorganizer/contact_sheet.py",
echo     "mediaorganizer/watermark.py",
echo     "mediaorganizer/repair.py",
echo     "mediaorganizer/mapview.py",
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

:: --- 4. Install deps + optional tools check + launch ----------------------
echo [4/4] Installing / updating dependencies...
pip install --quiet --exists-action i -r requirements.txt
if !errorlevel! neq 0 (
    echo   WARNING: Some packages may have failed. Tool may still work.
)
echo   done.
echo.

ffmpeg -version >nul 2>&1
if !errorlevel! neq 0 (
    echo  [INFO] ffmpeg not found -- video tools will be limited.
    echo  Download: https://ffmpeg.org/download.html  then add bin\ to PATH.
    echo.
)

curl -s http://localhost:11434/api/tags >nul 2>&1
if !errorlevel! neq 0 (
    echo  [INFO] Ollama not running -- AI descriptions will use heuristics.
    echo  To enable AI: https://ollama.ai  then: ollama pull moondream
    echo.
) else (
    echo  Ollama: running
    echo.
)

echo  Launching Media Organizer...
echo.
python -m mediaorganizer.gui

if !errorlevel! neq 0 (
    echo.
    echo  ERROR: The GUI failed to start. See the error above.
    echo  Paste the error into chat for help.
)

echo.
call .venv\Scripts\deactivate.bat 2>nul
pause
