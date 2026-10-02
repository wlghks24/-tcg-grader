@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 tcg_grader_autonomous_evolution_v391.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills
) else (
  python tcg_grader_autonomous_evolution_v391.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills
)
exit /b %errorlevel%
