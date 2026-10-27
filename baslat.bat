@echo off
rem Tuya Desktop App - konsol penceresi acmadan baslatir.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Once kur.ps1 dosyasini calistirin.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" light_app.py
