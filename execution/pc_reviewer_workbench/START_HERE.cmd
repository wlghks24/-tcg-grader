@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
cd /d "%~dp0"
py -3 -c "import sys,tkinter;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto PY_LAUNCHER
python -c "import sys,tkinter;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto PY_COMMAND
echo [HOLD] Python 3.10+ with Tkinter required. Run py --version.
goto FAILURE
:PY_LAUNCHER
py -3 -B "%~dp0preflight.py"
if errorlevel 1 goto FAILURE
py -3 -B "%~dp0local_gui.py"
set "RC=%ERRORLEVEL%"
goto DONE
:PY_COMMAND
python -B "%~dp0preflight.py"
if errorlevel 1 goto FAILURE
python -B "%~dp0local_gui.py"
set "RC=%ERRORLEVEL%"
:DONE
if "%RC%"=="0" exit /b 0
echo [HOLD] Program failed. Return code: %RC%
pause
exit /b %RC%
:FAILURE
pause
exit /b 2
