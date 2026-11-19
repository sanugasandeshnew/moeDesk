@echo off
cd /d "%~dp0"
if exist "moeDesk.exe" (
    start "" "moeDesk.exe"
) else (
    call BUILD_EXE.bat
)
