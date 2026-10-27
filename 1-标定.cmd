@echo off
REM ============================================================
REM   1-标定.cmd  —  分析模型在视频上的表现，给出 --conf-min 建议
REM   直接把视频文件拖到本文件上也可以运行。
REM ============================================================

cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

REM 默认视频路径，按需修改
set VIDEO=%~1
if "%VIDEO%"=="" set VIDEO=C:\Users\Lenovo\Desktop\摔倒参考 _ 50种摔倒方式.mp4

echo ============================================================
echo  标定模式（不判定事件，只统计模型输出）
echo  视频: %VIDEO%
echo ============================================================
echo.

"%PY%" tools\dry_run.py "%VIDEO%" --truth 50

echo.
echo ============================================================
echo  以上是完整输出。请把它整段复制给助手，用于确定 --conf-min。
echo ============================================================
pause
