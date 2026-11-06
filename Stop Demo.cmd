@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-demo.ps1" -Mode Stop
if errorlevel 1 (
    pause
    exit /b 1
)
