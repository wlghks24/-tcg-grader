@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
py -3 -c "import sys,tkinter;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto USING_PY
python -c "import sys,tkinter;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto USING_PYTHON
echo [ERROR] Python 3.10+ and tkinter are required.
goto FAIL
:USING_PY
py -3 "%~dp0full_repo_gui.py"
set "RC=%ERRORLEVEL%"
goto END
:USING_PYTHON
python "%~dp0full_repo_gui.py"
set "RC=%ERRORLEVEL%"
goto END
:END
if "%RC%"=="0" exit /b 0
echo [HOLD] GUI error code %RC%.
pause
exit /b %RC%
:FAIL
pause
exit /b 2
