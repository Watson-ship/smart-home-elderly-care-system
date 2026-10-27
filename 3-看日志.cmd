@echo off
REM ============================================================
REM   3-看日志.cmd  —  查看已记录的跌倒事件
REM ============================================================

cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

"%PY%" tools\query_events.py --limit 50

echo.
echo ============================================================
echo  原始日志文件: out\events.jsonl
echo ============================================================
pause
