@echo off
REM ============================================================
REM   2-跑视频.cmd  —  正式判定并写日志
REM
REM   参数（都可省略）：
REM       2-跑视频.cmd <视频路径> <conf-min> <fall-frames> <debounce>
REM
REM   默认值针对「50种摔倒方式」这类剪辑合集调过：
REM       conf-min    0.50   来自标定：Falldown 中位 0.658、p25 0.401
REM       fall-frames 20     压制模型横跳（标定显示平均每段仅 7.4 帧）
REM       debounce    5      类别多数表决，减少 Falldown/Sitting 抖动
REM
REM   如果判定次数远多于真实跌倒次数，把 conf-min 往上调（0.55 / 0.60）。
REM ============================================================

cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

set VIDEO=%~1
if "%VIDEO%"=="" set VIDEO=C:\Users\Lenovo\Desktop\摔倒参考 _ 50种摔倒方式.mp4

set CONFMIN=%~2
if "%CONFMIN%"=="" set CONFMIN=0.50

set FALLFRAMES=%~3
if "%FALLFRAMES%"=="" set FALLFRAMES=20

set DEBOUNCE=%~4
if "%DEBOUNCE%"=="" set DEBOUNCE=5

echo ============================================================
echo  判定模式
echo  视频        : %VIDEO%
echo  conf-min    : %CONFMIN%
echo  fall-frames : %FALLFRAMES%
echo  debounce    : %DEBOUNCE%
echo  其他        : --no-require-transition --cooldown 5（合集参数）
echo ============================================================
echo.

"%PY%" -m fallwatch.cli ^
  --source "%VIDEO%" ^
  --conf-min %CONFMIN% ^
  --fall-frames %FALLFRAMES% ^
  --debounce %DEBOUNCE% ^
  --no-require-transition ^
  --cooldown 5 ^
  --save-annotated out\annotated.mp4

echo.
echo ============================================================
echo  日志: out\events.jsonl 和 out\events.db
echo  视频: out\annotated.mp4
echo ============================================================
pause
