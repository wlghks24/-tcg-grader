@echo off
setlocal
cd /d "%~dp0"
echo Enter the full path of the OLD TCG_GRADER folder.
echo Example: C:\Users\YourName\Desktop\OLD_TCG_GRADER
set /p "OLD=Old folder: "
if not exist "%OLD%\tcg_updater.py" goto BAD_FOLDER
for %%F in (learning_store.json auto_repair_memory.json verification_history.json tcg_live_data.json) do (
  if exist "%OLD%\%%F" copy /y "%OLD%\%%F" "%~dp0%%F" >nul
)
if exist "%OLD%\.tcg_last_good" xcopy /e /i /y "%OLD%\.tcg_last_good" "%~dp0.tcg_last_good" >nul
echo [OK] Learning and recovery data copied to the new folder.
echo Run PC_SERVER_AUTO_START_INSTALL.bat in this new folder before deleting the old folder.
pause
exit /b 0
:BAD_FOLDER
echo [ERROR] The selected folder is not an old TCG_GRADER folder.
pause
exit /b 1
