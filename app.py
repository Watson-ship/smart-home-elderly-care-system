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
    右键本文件 → Run 'app'，然后在 Run 配置的 Parameters 里填：
        --source "C:/videos/demo.mp4" --conf-min 0.50 --fall-frames 20 --debounce 5 --no-require-transition --cooldown 5

不带参数运行会打印用法；改参数不用改代码，直接在 Run 配置的 Parameters 里改。
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


if __name__ == "__main__":
    # 不带参数时打印用法，避免使用别人电脑上不存在的默认视频路径
    if len(sys.argv) <= 1:
        print('用法: python app.py --source "视频路径" [其他参数]')
        print(
            '示例: python app.py --source "C:/videos/demo.mp4" '
            "--conf-min 0.50 --fall-frames 20 --debounce 5 "
            "--no-require-transition --cooldown 5"
        )
        print("查看全部参数: python app.py --help")
        sys.exit(0)

    argv = sys.argv[1:]

    missing = os.path.join(PROJECT_ROOT, "model", "best.pt")
    if not os.path.exists(missing):
        print(f"[错误] 找不到模型文件: {missing}")
        print("       请确认 model/best.pt 存在（约 22 MB），或运行: python tools/fetch_model.py")
        sys.exit(3)

    print(f"工作目录: {os.getcwd()}")
    print(f"参数    : {' '.join(argv)}\n")

    sys.argv = ["fallwatch"] + list(argv)
    runpy.run_module("fallwatch.cli", run_name="__main__", alter_sys=True)
