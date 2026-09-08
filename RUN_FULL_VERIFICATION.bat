@echo off
setlocal
cd /d "%~dp0"
title TCG CURRENT MAIN FULL VERIFICATION
echo Current main verification: active tablet runtime + security + current regression suite.
echo Node.js is optional. Set TCG_REQUIRE_NODE=1 for strict browser verification.
set "TCG_EXIT_CODE=1"
where py.exe >nul 2>nul
if errorlevel 1 goto CHECK_PYTHON
py.exe -3 -c "import sys; sys.exit(sys.version_info.major != 3)" >nul 2>nul
if not errorlevel 1 goto RUN_PY
:CHECK_PYTHON
where python.exe >nul 2>nul
if errorlevel 1 goto NO_PYTHON
python.exe -c "import sys; sys.exit(sys.version_info.major != 3)" >nul 2>nul
if not errorlevel 1 goto RUN_PYTHON
:NO_PYTHON
echo [ERROR] Python is not installed or PATH is missing.
goto END
:RUN_PY
py.exe -3 verify_current_runtime.py --passes 3
set "TCG_EXIT_CODE=%errorlevel%"
goto END
:RUN_PYTHON
python.exe verify_current_runtime.py --passes 3
set "TCG_EXIT_CODE=%errorlevel%"
:END
echo.
pause
endlocal & exit /b %TCG_EXIT_CODE%
