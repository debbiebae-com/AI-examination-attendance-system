@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-demo.ps1" -Mode Prepare -Desktop
if errorlevel 1 (
    echo.
    echo Desktop preparation did not finish. Read the message above before retrying.
    pause
    exit /b 1
)
echo.
pause
