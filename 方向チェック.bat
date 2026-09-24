@echo off
rem Double-click to check the XVF3000 direction (Ctrl+C to stop)
cd /d "%~dp0"
python tools\check_xvf3000.py
pause
