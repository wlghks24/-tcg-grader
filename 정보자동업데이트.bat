@echo off
setlocal
cd /d "%~dp0"
set "AUTO_MODE=0"
if /i "%~1"=="/AUTO" set "AUTO_MODE=1"
title TCG AUTO UPDATE
echo ========================================
echo TCG DATA AUTO UPDATE - 6 STEPS
echo 1 Release date
echo 2 Sale and re-release tracking
echo 3 Current market prices
echo 4 Promo and collaboration events
echo 5 Purchase sources and link security
echo 6 KRW exchange rates
echo ========================================
echo.
where py.exe >nul 2>nul
if not errorlevel 1 goto RUN_PY_LAUNCHER
where python.exe >nul 2>nul
if not errorlevel 1 goto RUN_PYTHON
echo [ERROR] Python is not installed or PATH is missing.
echo Install Python and enable Add Python to PATH.
goto END

:RUN_PY_LAUNCHER
py.exe -3 auto_update_all.py
goto RESULT

:RUN_PYTHON
python.exe auto_update_all.py

:RESULT
if errorlevel 1 goto FAILED
where py.exe >nul 2>nul
if not errorlevel 1 py.exe -3 verify_all.py
if errorlevel 1 python.exe verify_all.py
if errorlevel 1 goto FAILED
echo.
echo [OK] Update completed.
echo Report: auto_update_report.json
goto END

:FAILED
echo.
echo [ERROR] Update failed. Check auto_update_issues.json.

:END
echo.
if "%AUTO_MODE%"=="1" goto AUTO_EXIT
pause
:AUTO_EXIT
endlocal
