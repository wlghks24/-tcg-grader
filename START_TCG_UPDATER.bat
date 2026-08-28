@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "tcg_updater.py" goto MISSING_FILES
if not exist "index.html" goto MISSING_FILES
where py.exe >nul 2>nul
if errorlevel 1 goto CHECK_PYTHON
py.exe -3 -c "import sys; sys.exit(sys.version_info.major != 3)" >nul 2>nul
if errorlevel 1 goto CHECK_PYTHON
py.exe -3 tcg_updater.py
goto FINISH
:CHECK_PYTHON
where python.exe >nul 2>nul
if errorlevel 1 goto NO_PYTHON
python.exe -c "import sys; sys.exit(sys.version_info.major != 3)" >nul 2>nul
if errorlevel 1 goto NO_PYTHON
python.exe tcg_updater.py
goto FINISH
:MISSING_FILES
echo [ERROR] Extract every file from the ZIP before starting the server.
goto FAILED
:NO_PYTHON
echo [ERROR] Python 3 was not found. Install Python with Add Python to PATH enabled.
:FAILED
pause
exit /b 1
:FINISH
set "TCG_EXIT_CODE=%errorlevel%"
pause
exit /b %TCG_EXIT_CODE%
