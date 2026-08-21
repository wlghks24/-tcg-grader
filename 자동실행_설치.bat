@echo off
setlocal
cd /d "%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%STARTUP%\TCG_AUTO_UPDATE_START.cmd"
set "LOG=%~dp0TCG_AUTO_UPDATE_STARTUP.log"
(
  echo @echo off
  echo timeout /t 30 /nobreak ^>nul
  echo call "%~dp0TCG_AUTO_UPDATE.bat" /AUTO ^>^> "%LOG%" 2^>^&1
) > "%TARGET%"
if exist "%TARGET%" goto INSTALLED
echo [ERROR] Auto-start installation failed.
pause
exit /b 1

:INSTALLED
echo [OK] TCG auto update will run after Windows sign-in.
echo Startup file: %TARGET%
echo Log file: %LOG%
pause
endlocal
