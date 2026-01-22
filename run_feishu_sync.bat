@echo off
chcp 65001 >nul
echo =========================================
echo    飞书云文档周报同步工具
echo =========================================
echo.
echo 正在启动...
echo.

cd /d "%~dp0"
python feishu_sync.py

echo.
echo =========================================
echo 程序执行完毕，按任意键退出...
pause >nul
