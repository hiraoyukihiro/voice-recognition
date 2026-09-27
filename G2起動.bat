@echo off
rem ==== G2 direction + subtitle: start everything ====
rem 1) run.py (XVF3000 direction + subtitles)  2) G2 app server  3) QR code for the phone
cd /d "%~dp0"
for /f %%i in ('python tools\lan_ip.py') do set IP=%%i
echo PC IP: %IP%
start "run.py (do not close)" cmd /k python run.py
start "G2 app server (do not close)" /d "%~dp0g2app" cmd /k npx vite --host --port 5173
cd g2app
echo.
echo Scan this QR code with: Even Realities App - Even Hub tab - developer section (top right) - Scan QR
echo.
call npx evenhub qr --url http://%IP%:5173 -e
pause
