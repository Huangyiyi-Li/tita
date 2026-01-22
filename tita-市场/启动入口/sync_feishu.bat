@echo off
chcp 65001 >nul
echo 同步市场日志到飞书多维表格...
echo.

cd /d "%~dp0.."
python 工具脚本/sync_to_feishu.py

echo.
pause
