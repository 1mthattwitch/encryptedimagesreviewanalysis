@echo off
setlocal enabledelayedexpansion
title Gallery Vault Export Helper
cd /d "%~dp0"

echo.
echo  ============================================================
echo    Gallery Vault Export Helper
echo    Transfers your hidden files to your PC for processing
echo  ============================================================
echo.
echo  This tool helps you get your Gallery Vault files onto
echo  your PC. Choose one of two methods:
echo.
echo    [1]  In-app export  (easier -- no extra apps needed)
echo    [2]  ADB pull       (faster -- needs USB Debugging ON)
echo.
set /p CHOICE="  Your choice (1 or 2): "
echo.

if "%CHOICE%"=="1" goto IN_APP
if "%CHOICE%"=="2" goto ADB_PULL
echo  Invalid choice. Please run the script again and enter 1 or 2.
pause
exit /b 1

:: ────────────────────────────────────────────────────────────────────────────
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
goto DONE

:: ────────────────────────────────────────────────────────────────────────────
:ADB_PULL
echo  ============================================================
echo    Method 2: ADB Pull (USB Debugging)
echo  ============================================================
echo.

:: Check ADB
adb --version >nul 2>&1
if !errorlevel! neq 0 (
    echo  ERROR: ADB is not installed or not on PATH.
echo.
    echo  To install ADB:
    echo    1. Download Platform Tools from:
    echo       https://developer.android.com/tools/releases/platform-tools
    echo    2. Extract the zip (e.g. to C:\platform-tools)
    echo    3. Add that folder to your Windows PATH, OR
    echo       place adb.exe next to this bat file and run again.
    echo.
    pause
    exit /b 1
)
adb --version
echo.

:: Check device connected
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

:: Choose Gallery Vault path
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
echo  Destination: %~dp0GalleryVaultExport\
echo.
if not exist "GalleryVaultExport" mkdir GalleryVaultExport

echo  Pulling files... (this may take a while for large collections)
echo.
adb pull "!SRCPATH!" "%~dp0GalleryVaultExport\"

if !errorlevel! equ 0 (
    echo.
    echo  Transfer complete!
    echo  Opening output folder...
    explorer "%~dp0GalleryVaultExport"
) else (
    echo.
    echo  ADB pull encountered errors. The files may still have
    echo  transferred partially. Check the output folder:
    echo  %~dp0GalleryVaultExport\
    echo.
    echo  If you see an error about permissions, your files may
    echo  be encrypted in-app. Use Method 1 (in-app export) instead.
    explorer "%~dp0GalleryVaultExport"
)

:: ────────────────────────────────────────────────────────────────────────────
:DONE
echo.
echo  ============================================================
echo   NEXT STEP: Run run.bat and point it at:
echo   %~dp0GalleryVaultExport\
echo  ============================================================
echo.
pause
