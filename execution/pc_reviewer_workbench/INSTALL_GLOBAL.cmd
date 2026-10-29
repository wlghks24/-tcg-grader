@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto USING_PY
python -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto USING_PYTHON
echo [ERROR] Python 3.10+ required.
goto FAIL
:USING_PY
py -3 -B "%~dp0preflight.py"
if errorlevel 1 goto FAIL
py -3 -B "%~dp0install_global.py"
set "RC=%ERRORLEVEL%"
goto END
:USING_PYTHON
python -B "%~dp0preflight.py"
if errorlevel 1 goto FAIL
python -B "%~dp0install_global.py"
set "RC=%ERRORLEVEL%"
goto END
:END
if "%RC%"=="0" echo [OK] Open %%LOCALAPPDATA%%\TCG_PC_Reviewer_v092\START_HERE.cmd
pause
exit /b %RC%
:FAIL
pause
exit /b 2
