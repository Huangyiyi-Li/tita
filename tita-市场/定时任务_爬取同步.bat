@echo off
chcp 65001 >nul

cd /d "%~dp0.."

rem Create log directory if not exist
if not exist logs mkdir logs

rem Log file path (use UTF-8)
set LOGFILE=logs\scheduled_task.txt

rem Use PowerShell to write UTF-8 log entries
powershell -Command "[System.IO.File]::AppendAllText('%LOGFILE%', ('========================================' + [Environment]::NewLine), [System.Text.Encoding]::UTF8)"
powershell -Command "[System.IO.File]::AppendAllText('%LOGFILE%', ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] Task started' + [Environment]::NewLine), [System.Text.Encoding]::UTF8)"

rem Run Python with UTF-8 encoding
set PYTHONIOENCODING=utf-8

powershell -Command "[System.IO.File]::AppendAllText('%LOGFILE%', ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] Fetching Tita logs...' + [Environment]::NewLine), [System.Text.Encoding]::UTF8)"
python daily_log_aggregator.py >> "%LOGFILE%" 2>&1

powershell -Command "[System.IO.File]::AppendAllText('%LOGFILE%', ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] Syncing to Feishu...' + [Environment]::NewLine), [System.Text.Encoding]::UTF8)"
python 工具脚本/sync_to_feishu.py >> "%LOGFILE%" 2>&1

powershell -Command "[System.IO.File]::AppendAllText('%LOGFILE%', ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] Task completed' + [Environment]::NewLine + [Environment]::NewLine), [System.Text.Encoding]::UTF8)"
