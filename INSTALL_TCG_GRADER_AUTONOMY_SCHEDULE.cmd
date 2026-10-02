@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "TASK_NAME=TCG Grader Autonomy V393"
set "RUNNER=%~dp0TCG_GRADER_AUTONOMY.cmd"

if not exist "%RUNNER%" (
  echo [ERROR] TCG_GRADER_AUTONOMY.cmd not found.
  exit /b 2
)

schtasks /Create /F /TN "%TASK_NAME%" /SC HOURLY /MO 4 /RL LIMITED /TR "cmd.exe /d /c ^""%RUNNER%"^""
if errorlevel 1 (
  echo [ERROR] Failed to register Windows scheduled task.
  exit /b 1
)

echo [OK] "%TASK_NAME%" will run every 4 hours.
echo [INFO] Manual run: schtasks /Run /TN "%TASK_NAME%"
echo [INFO] Remove task: schtasks /Delete /F /TN "%TASK_NAME%"
exit /b 0
