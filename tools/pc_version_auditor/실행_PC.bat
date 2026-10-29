@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 pc_auditor\gui.py
if errorlevel 1 (
    echo.
    echo Python 3 / Tkinter / Git 설치를 확인하세요.
    pause
)
