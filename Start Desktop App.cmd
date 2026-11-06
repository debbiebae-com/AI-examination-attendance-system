@echo off
if not exist "%~dp0desktop\node_modules\electron\dist\electron.exe" (
    echo ExamLens Desktop is not prepared.
    echo Double-click Prepare Desktop App.cmd once while online, then try again.
    pause
    exit /b 1
)
start "" "%~dp0desktop\node_modules\electron\dist\electron.exe" "%~dp0desktop"
