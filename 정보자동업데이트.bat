@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo TCG 출시일·시세·프로모 행사·환율을 업데이트합니다.
where py >nul 2>nul
if %errorlevel%==0 (py auto_update_all.py) else (python auto_update_all.py)
echo.
echo 결과는 auto_update_report.json 파일에 저장되었습니다.
pause
