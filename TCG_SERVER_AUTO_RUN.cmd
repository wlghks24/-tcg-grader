@echo off
setlocal
title TCG Grader Auto Server
cd /d "%~dp0"
set "LOG=%~dp0TCG_SERVER_STARTUP.log"
echo [TCG] Waiting 30 seconds for Windows and Wi-Fi...
timeout /t 30 /nobreak >nul 2>nul
if not errorlevel 1 goto SELECT_PYTHON
ping 127.0.0.1 -n 31 >nul 2>nul
if errorlevel 1 goto WAIT_FAILURE

:SELECT_PYTHON
where py.exe >nul 2>nul
if errorlevel 1 goto CHECK_PYTHON
py.exe -3 -c "import sys; sys.exit(sys.version_info.major != 3)" >nul 2>nul
if errorlevel 1 goto CHECK_PYTHON
set "TCG_PYTHON_EXE=py.exe"
set "TCG_PYTHON_ARGS=-3"
goto RUN

:CHECK_PYTHON
where python.exe >nul 2>nul
if errorlevel 1 goto NO_PYTHON
python.exe -c "import sys; sys.exit(sys.version_info.major != 3)" >nul 2>nul
if errorlevel 1 goto NO_PYTHON
set "TCG_PYTHON_EXE=python.exe"
set "TCG_PYTHON_ARGS="

:RUN
if not exist "tcg_updater.py" goto MISSING_FILES
if not exist "index.html" goto MISSING_FILES
if exist "%LOG%" for %%I in ("%LOG%") do if %%~zI GTR 1048576 move /y "%LOG%" "%LOG%.old" >nul 2>nul
echo [TCG] Server is running. Keep this window open.
echo [TCG] PC: http://127.0.0.1:8765/index.html
echo [%date% %time%] Starting server with %TCG_PYTHON_EXE%.>>"%LOG%"
"%TCG_PYTHON_EXE%" %TCG_PYTHON_ARGS% tcg_updater.py >>"%LOG%" 2>&1
:STOPPED
echo [TCG] Server stopped. Restarting in 10 seconds...
echo [%date% %time%] Server stopped; restart scheduled.>>"%LOG%"
timeout /t 10 /nobreak >nul 2>nul
if not errorlevel 1 goto RUN
ping 127.0.0.1 -n 11 >nul 2>nul
if errorlevel 1 goto WAIT_FAILURE
goto RUN

:NO_PYTHON
echo [ERROR] A working Python 3 interpreter was not found. Automatic restart stopped.
echo [%date% %time%] Python 3 missing or broken; restart loop stopped.>>"%LOG%"
exit /b 1

:MISSING_FILES
echo [ERROR] Required server files are missing. Automatic restart stopped.
echo [%date% %time%] Required server files missing; restart loop stopped.>>"%LOG%"
exit /b 1

:WAIT_FAILURE
echo [ERROR] Windows wait commands failed. Restart loop stopped to prevent rapid retries.
echo [%date% %time%] Restart delay unavailable; rapid retry blocked.>>"%LOG%"
exit /b 1
