@echo off
setlocal
title TCG Grader Auto Server
cd /d "%~dp0"
set "LOG=%~dp0TCG_SERVER_STARTUP.log"
echo [TCG] Waiting 30 seconds for Windows and Wi-Fi...
timeout /t 30 /nobreak >nul

:RUN
echo [TCG] Server is running. Keep this window open.
echo [TCG] PC: http://127.0.0.1:8765/index.html
echo [%date% %time%] Starting server.>>"%LOG%"
where py.exe >nul 2>nul
if errorlevel 1 goto RUN_PYTHON
py.exe -3 tcg_updater.py >>"%LOG%" 2>&1
goto STOPPED
:RUN_PYTHON
python.exe tcg_updater.py >>"%LOG%" 2>&1
:STOPPED
echo [TCG] Server stopped. Restarting in 10 seconds...
echo [%date% %time%] Server stopped; restart scheduled.>>"%LOG%"
timeout /t 10 /nobreak >nul
goto RUN
