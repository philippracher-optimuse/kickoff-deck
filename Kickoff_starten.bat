@echo off
rem Kick-off tool - double-click to start. You can also drag a project folder onto this file.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\start.ps1" "%~1"
echo.
pause
