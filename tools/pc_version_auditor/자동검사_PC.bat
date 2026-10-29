@echo off
chcp 65001 >nul
cd /d "%~dp0"
set /p TCG_REPO=TCG Git repository folder (example C:\tcg-grader): 
set /p TCG_OUT=Report folder outside repository (example C:\TCG_PC_REPORT): 
set /p TCG_LAST=Last documented V number, Enter for ledger maximum: 
if "%TCG_REPO%"=="" goto :bad
if "%TCG_OUT%"=="" goto :bad
if "%TCG_LAST%"=="" (
  py -3 pc_auditor\audit.py --repo "%TCG_REPO%" --output "%TCG_OUT%" --auto
) else (
  py -3 pc_auditor\audit.py --repo "%TCG_REPO%" --output "%TCG_OUT%" --latest %TCG_LAST% --auto
)
pause
exit /b %errorlevel%
:bad
echo Both repository and output folders are required.
pause
exit /b 2
