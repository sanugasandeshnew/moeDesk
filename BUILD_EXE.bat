@echo off
title Building moeDesk Windows Setup Installer
cd /d "%~dp0"

echo ===================================================
echo             moeDesk Build Pipeline
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
)

echo [1/3] Ensuring dependencies and PyInstaller...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt pyinstaller

echo [2/3] Compiling moeDesk binaries with PyInstaller...
".venv\Scripts\pyinstaller.exe" ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name "moeDesk" ^
    --icon="app_icon.ico" ^
    --add-data "app_icon.ico;." ^
    --add-data "app_icon.png;." ^
    --collect-submodules PySide6.QtMultimedia ^
    --collect-submodules PySide6.QtMultimediaWidgets ^
    --hidden-import PySide6.QtMultimedia ^
    --hidden-import PySide6.QtMultimediaWidgets ^
    --hidden-import cloudscraper ^
    --hidden-import bs4 ^
    --hidden-import psutil ^
    livewallpaper.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller compilation failed! Check output above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Compiling Setup Installer with Inno Setup...

set "ISCC_PATH="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if defined ISCC_PATH (
    "%ISCC_PATH%" moedesk_setup.iss
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ===================================================
        echo [SUCCESS] Windows Setup Installer is ready!
        echo Location: Output\moeDesk_Setup_v1.0.0.exe
        echo ===================================================
        echo.
    ) else (
        echo [ERROR] Inno Setup compilation failed!
    )
) else (
    echo.
    echo [NOTE] Inno Setup was not found in standard paths.
    echo Compiled binaries are ready in: dist\moeDesk\
    echo To build the installer wizard, install Inno Setup and open 'moedesk_setup.iss'.
    echo.
)

pause
