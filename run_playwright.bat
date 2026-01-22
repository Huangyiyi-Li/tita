@echo off
chcp 65001 >nul
echo =========================================
echo    Playwright 自动周报生成器
echo =========================================
echo.
echo 正在启动...
echo.

cd /d "%~dp0"
python playwright_weekly_report.py

echo.
echo =========================================
echo 程序执行完毕，按任意键退出...
pause >nul
