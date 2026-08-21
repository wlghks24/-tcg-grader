@echo off
setlocal
cd /d "%~dp0"
echo Enter the full path of the OLD TCG_GRADER folder.
echo Example: C:\Users\YourName\Desktop\OLD_TCG_GRADER
set /p "OLD=Old folder: "
set "OLD=%OLD:"=%"
if not exist "%OLD%\tcg_updater.py" goto BAD_FOLDER
if /i "%OLD%\"=="%~dp0" goto SAME_FOLDER
where py.exe >nul 2>nul
if not errorlevel 1 goto RUN_PY
where python.exe >nul 2>nul
if errorlevel 1 goto NO_PYTHON
python.exe "%~dp0migrate_old_data.py" "%OLD%" "%~dp0"
goto RESULT
:RUN_PY
py.exe -3 "%~dp0migrate_old_data.py" "%OLD%" "%~dp0"
:RESULT
if errorlevel 1 goto MIGRATE_FAILED
echo Run PC_SERVER_AUTO_START_INSTALL.bat in this new folder before deleting the old folder.
pause
exit /b 0
:BAD_FOLDER
echo [ERROR] The selected folder is not an old TCG_GRADER folder.
pause
exit /b 1
:SAME_FOLDER
echo [ERROR] Old and new folders are the same. Select the older folder.
pause
exit /b 1
:NO_PYTHON
echo [ERROR] Python 3 was not found.
pause
exit /b 1
:MIGRATE_FAILED
echo [ERROR] Migration failed. No old folder was deleted.
pause
exit /b 1
