@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Install it from https://www.python.org/downloads/
  echo IMPORTANT: tick "Add python.exe to PATH" in the installer, then run this again.
  pause
  exit /b
)
if not exist ".venv\Scripts\pythonw.exe" (
  echo First run: setting up, this takes 1-2 minutes...
  python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
start "" ".venv\Scripts\pythonw.exe" livewallpaper.py
