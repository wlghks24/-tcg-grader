@echo off
setlocal
cd /d "%~dp0"
title TCG AUTO UPDATE
echo ========================================
echo TCG DATA AUTO UPDATE
echo Release - Market Price - Promo - FX
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
echo.
echo [OK] Update completed.
echo Report: auto_update_report.json
goto END

:FAILED
echo.
echo [ERROR] Update failed. Check auto_update_issues.json.

:END
echo.
pause
endlocal
