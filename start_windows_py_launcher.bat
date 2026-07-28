@echo off
setlocal
title Smart Export CRM V7.2 - OUTLOOK DESKTOP
cd /d "%~dp0"
set CRM_PORT=5050
py -3 app.py
pause
