@echo off
setlocal
title Smart Export CRM V7.2 - OUTLOOK DESKTOP
cd /d "%~dp0"
set CRM_PORT=5050
start "" "http://127.0.0.1:5050/version"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 app.py
) else (
  python app.py
)
pause
