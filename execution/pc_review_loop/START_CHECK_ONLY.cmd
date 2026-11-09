@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -X utf8 "%~dp0runner.py" --static-only %*
goto finished
:usepython
python -X utf8 "%~dp0runner.py" --static-only %*
:finished
pause
