@echo off
title Intel Bureau - one click setup
cd /d "%~dp0"
if not exist "%~dp0scripts\first-run.ps1" goto nofiles
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\first-run.ps1" %*
set RC=%ERRORLEVEL%
if "%RC%"=="0" goto done
echo.
echo [FAILED, exit code %RC%] Please screenshot this window and send it to the person who gave you this package.
pause
goto done
:nofiles
echo Cannot find scripts\first-run.ps1 next to this file.
echo Please unzip the whole package first, do not run this from inside the zip.
pause
set RC=1
:done
exit /b %RC%