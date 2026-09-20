@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where py.exe >nul 2>nul
if not errorlevel 1 (
  py.exe -3 runtime_device_benchmark.py --label windows-pc %*
  exit /b %errorlevel%
)

where python.exe >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3 was not found.
  exit /b 1
)
python.exe runtime_device_benchmark.py --label windows-pc %*
exit /b %errorlevel%
