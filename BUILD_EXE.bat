@echo off
title Building moeDesk Standalone Executable
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

echo [2/3] Compiling moeDesk to standalone Portable Executable...
".venv\Scripts\pyinstaller.exe" ^
    --noconfirm ^
    --onefile ^
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

if %ERRORLEVEL% EQU 0 (
    if exist "dist\moeDesk.exe" (
        copy /y "dist\moeDesk.exe" "moeDesk.exe" >nul
    )
    echo.
    echo ===================================================
    echo [3/3] Build Successful!
    echo Standalone Portable Executable is ready:
    echo   - moeDesk.exe
    echo   - dist\moeDesk.exe
    echo.
    echo No installation needed! Just double-click moeDesk.exe
    echo ===================================================
    echo.
) else (
    echo.
    echo [ERROR] Build failed! Check the log output above.
)

pause
