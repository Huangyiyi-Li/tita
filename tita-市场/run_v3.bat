@echo off
chcp 65001 >nul
echo ============================================================
echo       日报分析系统 v3.0 - 启动器
echo       (双跑一致性 + 标签自生长)
echo ============================================================

cd /d "%~dp0.."

echo.
echo [1/6] 检查数据库结构...
python upgrade_schema_v3.py

echo.
echo [2/6] 开始双跑事件抽取 (每条日志两次API调用)...
echo       这可能需要较长时间，请耐心等待...
python extract_events_v3.py

echo.
echo [3/6] 执行标签晋升检查...
python promote_tags.py

echo.
echo [4/6] 别名自动发现...
python discover_aliases.py

echo.
echo [5/6] 启动Web服务...
echo       质量监控: http://localhost:8080/输出/quality_dashboard.html
echo       机会看板: http://localhost:8080/输出/opportunity_dashboard.html

echo.
echo [6/6] 打开质量监控面板...
start http://localhost:8080/输出/quality_dashboard.html

echo.
echo ============================================================
echo   服务已启动！请勿关闭此窗口。
echo ============================================================
python -m http.server 8080
