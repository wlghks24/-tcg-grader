@echo off
setlocal
cd /d "%~dp0"
if not exist "tcg_updater.py" goto BAD_FOLDER
if not exist "index.html" goto BAD_FOLDER
if not exist "TCG_SERVER_AUTO_RUN.cmd" goto BAD_FOLDER
where py.exe >nul 2>nul
if not errorlevel 1 goto PY_OK
where python.exe >nul 2>nul
if errorlevel 1 goto NO_PYTHON
:PY_OK
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%STARTUP%\TCG_SERVER_AUTO_START.cmd"
set "OLD_TARGET=%STARTUP%\TCG_AUTO_UPDATE_START.cmd"
if exist "%OLD_TARGET%" del /q "%OLD_TARGET%"
>"%TARGET%" echo @echo off
>>"%TARGET%" echo call "%~dp0TCG_SERVER_AUTO_RUN.cmd"
if not exist "%TARGET%" goto INSTALL_FAILED
echo [OK] TCG server auto-start installed.
echo It starts 30 seconds after sign-in and restarts after an error.
echo Program folder: %~dp0
echo Startup file: %TARGET%
pause
exit /b 0
:BAD_FOLDER
echo [ERROR] Required files are missing.
echo Put this installer inside the fully extracted TCG_GRADER folder and run it again.
pause
exit /b 1
:NO_PYTHON
echo [ERROR] Python 3 was not found. Install Python with Add Python to PATH enabled.
pause
exit /b 1
:INSTALL_FAILED
echo [ERROR] Could not create the Windows startup file.
pause
exit /b 1
