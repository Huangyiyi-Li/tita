@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "weekly_report_generator.ps1"
pause
