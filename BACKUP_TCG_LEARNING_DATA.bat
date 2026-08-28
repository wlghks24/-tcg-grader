@echo off
setlocal
cd /d "%~dp0"
set "DEST=%~dp0TCG_LEARNING_BACKUP"
if not exist "%DEST%" mkdir "%DEST%"
for %%F in (learning_store.json auto_repair_memory.json verification_history.json tcg_live_data.json) do (
  if exist "%%F" copy /y "%%F" "%DEST%\%%F" >nul
)
if exist ".tcg_last_good" xcopy /e /i /y ".tcg_last_good" "%DEST%\.tcg_last_good" >nul
echo [OK] Learning data backup: %DEST%
pause
