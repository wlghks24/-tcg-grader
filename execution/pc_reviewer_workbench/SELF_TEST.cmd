@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
cd /d "%~dp0"
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto PY_LAUNCHER
python -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto PY_COMMAND
echo [HOLD] Python 3.10+ required.
goto FAIL
:PY_LAUNCHER
py -3 -B -m unittest discover -s tests -v
set "RC=%ERRORLEVEL%"
goto DONE
:PY_COMMAND
python -B -m unittest discover -s tests -v
set "RC=%ERRORLEVEL%"
:DONE
if "%RC%"=="0" echo [OK] Tests passed.
if not "%RC%"=="0" echo [HOLD] Tests failed: %RC%
pause
exit /b %RC%
:FAIL
pause
exit /b 2
