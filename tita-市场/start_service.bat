@echo off
chcp 65001 >nul
title Tita日报分析服务

echo ============================================
echo   🚀 Tita日报分析一体化服务
echo ============================================
echo.
echo 启动后请访问: http://localhost:8080
echo.
echo 按 Ctrl+C 可停止服务
echo ============================================
echo.

cd /d "%~dp0.."
python tita_service.py

pause
