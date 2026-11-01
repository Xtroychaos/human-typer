@echo off
rem Double-click this file to open Human Typer on Windows.
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)

%PY% --version >nul 2>nul
if not %errorlevel%==0 (
    echo Python is not installed.
    echo Get it free from https://www.python.org/downloads/ and tick "Add Python to PATH" when installing.
    pause
    exit /b 1
)

echo Getting things ready (only slow the first time)...
%PY% -m pip install --quiet --disable-pip-version-check pynput

start "" %PY%w human_typer.py
