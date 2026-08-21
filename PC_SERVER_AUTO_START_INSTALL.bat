@echo off
setlocal
cd /d "%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%STARTUP%\TCG_SERVER_AUTO_START.cmd"
set "OLD_TARGET=%STARTUP%\TCG_AUTO_UPDATE_START.cmd"
set "LOG=%~dp0TCG_SERVER_STARTUP.log"
if exist "%OLD_TARGET%" del /q "%OLD_TARGET%"
(
  echo @echo off
  echo timeout /t 30 /nobreak ^>nul
  echo cd /d "%~dp0"
  echo where py.exe ^>nul 2^>nul
  echo if not errorlevel 1 py.exe -3 tcg_updater.py ^>^> "%LOG%" 2^>^&1
  echo if errorlevel 1 python.exe tcg_updater.py ^>^> "%LOG%" 2^>^&1
) > "%TARGET%"
if exist "%TARGET%" goto INSTALLED
echo [ERROR] Auto-start installation failed.
pause
exit /b 1

:INSTALLED
echo [OK] TCG server will start 30 seconds after Windows sign-in.
echo The server updates immediately and every 6 hours while running.
echo Startup file: %TARGET%
echo Log file: %LOG%
pause
endlocal
