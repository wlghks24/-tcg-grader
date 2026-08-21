@echo off
setlocal
set "TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\TCG_SERVER_AUTO_START.cmd"
set "OLD_TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\TCG_AUTO_UPDATE_START.cmd"
if exist "%TARGET%" del /q "%TARGET%"
if exist "%OLD_TARGET%" del /q "%OLD_TARGET%"
if exist "%TARGET%" goto FAILED
echo [OK] TCG server auto-start has been removed from Windows startup.
pause
exit /b 0

:FAILED
echo [ERROR] Could not remove the startup file.
pause
exit /b 1
