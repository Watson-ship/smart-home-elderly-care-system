@echo off
REM ============================================================
REM   run.cmd  —  通用启动器
REM   用法：把参数直接接在后面，例如
REM       run.cmd -m fallwatch.cli --source "D:\video.mp4"
REM   作用是自动使用 .venv 里的 Python，并把控制台切到 UTF-8，
REM   这样中文不会乱码。
REM ============================================================

REM 切到脚本所在目录（\fall-watch）
cd /d "%~dp0"

REM 控制台代码页切到 UTF-8
chcp 65001 >nul

REM 让 Python 的输入输出都用 UTF-8
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM 优先用虚拟环境里的 Python，没有就退回系统 Python
set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

"%PY%" %*
set EXITCODE=%ERRORLEVEL%

if not "%1"=="" goto :eof
pause
