@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -X utf8 "%~dp0runner.py" --ai --publish-draft %*
goto finished
:usepython
where python >nul 2>nul
if errorlevel 1 goto missing
python -X utf8 "%~dp0runner.py" --ai --publish-draft %*
goto finished
:missing
echo Python 3.11 or newer is required. See README_KO.md.
:finished
echo.
echo Results: %%LOCALAPPDATA%%\TCG_PC_Review
pause
