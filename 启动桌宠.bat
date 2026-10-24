@echo off
rem ============================================
rem  Desktop Pet launcher
rem  Run this file (double-click) to start it.
rem  Requires Python 3 installed with PATH.
rem ============================================
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python desktoppet_launcher.py
    exit /b
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py desktoppet_launcher.py
    exit /b
)

echo Python 3 was not found on PATH.
echo Please install Python 3 (tick "Add python.exe to PATH").
echo Download: https://www.python.org/downloads/
pause