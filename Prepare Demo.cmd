@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-demo.ps1" -Mode Prepare
if errorlevel 1 (
    echo.
    echo Preparation did not finish. Read the message above before retrying.
    pause
    exit /b 1
)
echo.
pause
