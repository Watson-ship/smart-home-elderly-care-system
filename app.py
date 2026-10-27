"""PyCharm 专用入口 —— 直接在 IDE 里点运行即可。

为什么需要这个文件：
    本项目的判定代码在 fallwatch/ 包内，包内用的是相对导入
    （from . import config）。如果直接用 PyCharm 打开 fallwatch/cli.py
    并点运行，Python 会把它当独立脚本执行，相对导入立刻报
    ImportError: attempted relative import with no known parent package。
    另外 cli.py 里所有路径（model/best.pt、out/）都是相对于当前工作目录的，
    而 PyCharm 默认把「脚本所在目录」设为工作目录，会导致找不到模型。

这个文件放在项目根目录，解决两件事：
    1. 用 runpy 以模块方式执行 fallwatch.cli，相对导入正常工作；
    2. 强制把工作目录切到项目根目录，模型和输出路径就都对得上。

用法（在 PyCharm 里）：
    右键本文件 → Run 'app'。
    或在下方 Run 配置里把 Parameters 填成：
        --source "C:\\Users\\Lenovo\\Desktop\\摔倒参考 _ 50种摔倒方式-00.00.02.847-00.00.20.567.mp4" --conf-min 0.50 --fall-frames 20 --debounce 5 --no-require-transition --cooldown 5

改参数不用改代码：直接在 Run 配置的 Parameters 里改。
"""

from __future__ import annotations

import os
import runpy
import sys

# 直接把本文件所在目录（项目根）设为工作目录，避免依赖 PyCharm 的设置
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

# 保证能 import fallwatch 包
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 让控制台按 UTF-8 输出，避免 PyCharm Run 窗口里中文变乱码
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 没带参数时给一套默认参数，这样直接点运行也能出结果
DEFAULT_ARGS = [
    "--source",
    r"C:\Users\Lenovo\Desktop\摔倒参考 _ 50种摔倒方式-00.00.02.847-00.00.20.567.mp4",
    "--conf-min", "0.50",
    "--fall-frames", "20",
    "--debounce", "5",
    "--no-require-transition",
    "--cooldown", "5",
]

if __name__ == "__main__":
    argv = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_ARGS

    missing = os.path.join(PROJECT_ROOT, "model", "best.pt")
    if not os.path.exists(missing):
        print(f"[错误] 找不到模型文件: {missing}")
        print("       请确认 model/best.pt 存在（约 21.5 MB）。")
        sys.exit(3)

    print(f"工作目录: {os.getcwd()}")
    print(f"参数    : {' '.join(argv)}\n")

    sys.argv = ["fallwatch"] + list(argv)
    runpy.run_module("fallwatch.cli", run_name="__main__", alter_sys=True)
