@echo off
rem Box2Box version 1.0
rem Starts Box2Box with this project's own Python environment.
rem Drag a .fm save onto this file to open it straight away.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo The Python environment is missing. In this folder, run:
    echo     py -3.14 -m venv .venv
    echo     .venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "fm_review.py" %*
