@echo off
setlocal
title Smart Export CRM V7.2 - OUTLOOK DESKTOP
cd /d "%~dp0"
set CRM_PORT=5050
echo =====================================================
echo Smart Export CRM V7.2 - OUTLOOK DESKTOP APP
echo Open: http://127.0.0.1:5050
echo Email drafts will open in the Windows MAILTO app.
echo Set Microsoft Outlook as the MAILTO default.
echo =====================================================
echo.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 app.py
  goto END
)
where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
  goto END
)
echo Python could not be found.
echo Install Python 3 and tick "Add python.exe to PATH".
:END
echo.
echo Verify: http://127.0.0.1:5050/version
pause
