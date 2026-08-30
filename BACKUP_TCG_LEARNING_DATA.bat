@echo off
setlocal
cd /d "%~dp0"
set "DEST=%~dp0TCG_LEARNING_BACKUP"
if not exist "%DEST%" mkdir "%DEST%"
for %%F in (learning_store.json card_identity_learning.json graded_photo_reference_learning.json graded_photo_source_learning.json detailed_collection_learning.json detailed_collection_learning.json.bak collection_learning_memory.json collection_learning_memory.json.bak search_method_learning.json search_method_learning.json.bak search_engine_profile.json verified_certifications.json library_verified_slab_references.json manual_graded_photo_registrations.json auto_repair_memory.json verification_history.json tcg_live_data.json) do (
  if exist "%%F" copy /y "%%F" "%DEST%\%%F" >nul
)
if exist ".tcg_last_good" xcopy /e /i /y ".tcg_last_good" "%DEST%\.tcg_last_good" >nul
if exist "GRADE_TRAINING_INBOX" xcopy /e /i /y "GRADE_TRAINING_INBOX" "%DEST%\GRADE_TRAINING_INBOX" >nul
echo [OK] Learning data backup: %DEST%
pause
