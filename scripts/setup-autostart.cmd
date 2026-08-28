@echo off
REM Double-click this to make the digest runner start automatically at login.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-autostart.ps1"
echo.
pause
