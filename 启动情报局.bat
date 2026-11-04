@echo off
title Intel Bureau workbench
cd /d "%~dp0"
if not exist "%~dp0scripts\start.ps1" goto nofiles
if not exist "%~dp0.venv\Scripts\python.exe" goto firstrun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
set RC=%ERRORLEVEL%
if "%RC%"=="0" goto done
echo.
echo [FAILED, exit code %RC%] Please screenshot this window and send it to the person who gave you this package.
echo You can also run .venv\Scripts\python.exe -X utf8 -m bureau doctor to see why.
pause
goto done
:firstrun
if not exist "%~dp0scripts\first-run.ps1" goto noinstall
echo First run detected, setting up first. This takes a few minutes, please do not close this window.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\first-run.ps1" %*
set RC=%ERRORLEVEL%
if "%RC%"=="0" goto done
pause
goto done
:noinstall
echo The workbench is not installed yet. Please run the one click setup bat in this folder first.
pause
set RC=1
goto done
:nofiles
echo Cannot find scripts\start.ps1 next to this file.
echo Please unzip the whole package first, do not run this from inside the zip.
pause
set RC=1
:done
exit /b %RC%
