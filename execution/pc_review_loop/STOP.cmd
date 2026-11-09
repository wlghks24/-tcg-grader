@echo off
setlocal
set "PYTHONUTF8=1"
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -X utf8 "%~dp0runner.py" --stop %*
goto finished
:usepython
python -X utf8 "%~dp0runner.py" --stop %*
:finished
pause
