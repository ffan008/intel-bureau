@echo off
title Feishu re-authorization - Intel Bureau
cd /d "%~dp0"
if not exist "%~dp0scripts\feishu-reauth.ps1" goto nofiles
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\feishu-reauth.ps1" %*
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" goto ok
echo [FAILED, exit code %RC%] Press any key to close this window.
goto wait
:ok
echo [DONE] Press any key to close this window.
:wait
pause >nul
goto done
:nofiles
echo Cannot find scripts\feishu-reauth.ps1 next to this file.
echo Please unzip the whole package first, do not run this from inside the zip.
pause
set RC=1
:done
exit /b %RC%
