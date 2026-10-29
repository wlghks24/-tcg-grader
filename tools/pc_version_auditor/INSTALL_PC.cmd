@echo off
setlocal DisableDelayedExpansion
py -3 "%~dp0install_local.py"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
