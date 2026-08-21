@echo off
setlocal
cd /d "%~dp0"
title TCG FULL VERIFICATION
where py.exe >nul 2>nul
if not errorlevel 1 goto RUN_PY
where python.exe >nul 2>nul
if not errorlevel 1 goto RUN_PYTHON
echo [ERROR] Python is not installed or PATH is missing.
goto END
:RUN_PY
py.exe -3 verify_all.py
goto END
:RUN_PYTHON
python.exe verify_all.py
:END
echo.
pause
endlocal
