@echo off
chcp 65001 >nul
echo 正在启动周报生成脚本...
python weekly_report_generator.py
echo.
pause
