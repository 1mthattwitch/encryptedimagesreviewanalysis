@echo off
setlocal enabledelayedexpansion
title Gallery Vault Export Helper

echo.
echo  ============================================================
echo   Gallery Vault Export Helper
echo   Exports your Gallery Vault files for use with Media Organizer
echo  ============================================================
echo.
echo  Choose export method:
echo.
echo  [1] Gallery Vault in-app export (recommended, no USB debugging needed)
echo  [2] ADB pull via USB (requires USB Debugging enabled on phone)
echo.
set /p CHOICE="Enter 1 or 2: "

if "%CHOICE%"=="1" goto :inapp
if "%CHOICE%"=="2" goto :adb
echo Invalid choice. Exiting.
pause & exit /b 1

:: ── Option 1: In-app export guide ────────────────────────────────────────────
:inapp
echo.
echo  ── Gallery Vault In-App Export ─────────────────────────────────
echo.
echo  Step 1: Open Gallery Vault on your phone
echo  Step 2: Tap the three-dot menu (⋮) in the top-right corner
echo  Step 3: Select "Backup / Restore" or "Export"
echo  Step 4: Choose "Export to Gallery" or "Export to Device Storage"
echo  Step 5: Select ALL files → Confirm export
echo          Files will appear in your phone's regular Photos / Downloads
echo.
echo  Step 6: Connect phone to PC via USB cable
echo  Step 7: On your phone, choose "File Transfer" / "MTP" mode
echo  Step 8: Open File Explorer → This PC → [Your Phone] → Internal Storage
echo  Step 9: Find the exported files (usually in DCIM\, Downloads\, or
echo           the folder you chose in Step 5)
echo  Step 10: Copy everything to the folder below
echo.

set OUTDIR=%~dp0GalleryVaultExport
if not exist "%OUTDIR%" mkdir "%OUTDIR%"
echo  Output folder: %OUTDIR%
echo.
echo  Press any key once you have copied the files there...
pause >nul
echo.

if exist "%OUTDIR%\*.*" (
    for /f %%A in ('dir /a-d /s /b "%OUTDIR%" 2^>nul ^| find /c /v ""') do set COUNT=%%A
    echo  Found !COUNT! files in %OUTDIR%
) else (
    echo  [WARN] No files found yet — check the folder and re-run if needed.
)
goto :done

:: ── Option 2: ADB pull ────────────────────────────────────────────────────────
:adb
echo.
echo  ── ADB Pull ────────────────────────────────────────────────────
echo.

:: Check adb
adb --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] adb not found.
    echo  Install Android Platform Tools:
    echo  https://developer.android.com/studio/releases/platform-tools
    echo  Extract and add to PATH, then re-run this script.
    pause & exit /b 1
)
echo  adb found.
echo.

:: Check device
adb devices 2>nul | findstr /v "List of" | findstr "device" >nul 2>&1
if errorlevel 1 (
    echo  No device detected. Make sure:
    echo   - USB Debugging is enabled (Settings → Developer Options → USB Debugging)
    echo   - Phone is connected via USB
    echo   - You accept the "Allow USB Debugging" prompt on the phone
    echo.
    echo  Press any key to retry...
    pause >nul
    adb devices
)

echo.
echo  Common Gallery Vault storage paths:
echo.
echo  [1] /sdcard/.GalleryVault/        (hidden, most common)
echo  [2] /sdcard/GalleryVault/         (some versions)
echo  [3] /sdcard/Android/data/com.lu.protect.image.fp/files/
echo  [4] Enter custom path
echo.
set /p PATHCHOICE="Enter 1-4: "

if "%PATHCHOICE%"=="1" set SRCPATH=/sdcard/.GalleryVault/
if "%PATHCHOICE%"=="2" set SRCPATH=/sdcard/GalleryVault/
if "%PATHCHOICE%"=="3" set SRCPATH=/sdcard/Android/data/com.lu.protect.image.fp/files/
if "%PATHCHOICE%"=="4" (
    set /p SRCPATH="Enter path: "
)

echo.
echo  Pulling from: %SRCPATH%
set OUTDIR=%~dp0GalleryVaultExport
if not exist "%OUTDIR%" mkdir "%OUTDIR%"
echo  Saving to:    %OUTDIR%
echo.

adb pull "%SRCPATH%" "%OUTDIR%"
if errorlevel 1 (
    echo.
    echo  [ERROR] adb pull failed. The path may not exist on this device.
    echo  Try option [4] with a custom path, or use Option 1 (in-app export).
    pause & exit /b 1
)

for /f %%A in ('dir /a-d /s /b "%OUTDIR%" 2^>nul ^| find /c /v ""') do set COUNT=%%A
echo.
echo  Pulled !COUNT! files to %OUTDIR%

:done
echo.
echo  ────────────────────────────────────────────────────────────
echo   All done! Now run run.bat and point it at:
echo   %OUTDIR%
echo  ────────────────────────────────────────────────────────────
echo.
explorer "%OUTDIR%" 2>nul
pause
