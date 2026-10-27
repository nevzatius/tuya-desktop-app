@echo off
rem Odamdaki Isik - konsolla baslatir (hata mesajlarini gormek icin).
cd /d "%~dp0"
".venv\Scripts\python.exe" light_app.py
pause
