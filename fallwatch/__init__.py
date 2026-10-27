"""fall-watch：单机跌倒检测与日志系统。

只依赖笔记本摄像头 + CPU，不需要 RK3588 / NPU / MQTT / 摄像头硬件模组。

模块划分：
    config        所有可调阈值集中在此
    detector      模型加载与推理，对外输出统一结构
    state_machine 核心判定：窗口 + 轨迹 + 场景切换 + 冷却
    logger        JSONL + SQLite 双写与抓拍
    cli           命令行入口
"""

from . import config  # noqa: F401
from .detector import Detection, Detector  # noqa: F401
from .logger import EventLogger  # noqa: F401
from .state_machine import FallEvent, FallStateMachine, iou  # noqa: F401

__version__ = "1.0.0"

__all__ = [
    "config",
    "Detection",
    "Detector",
    "EventLogger",
    "FallEvent",
    "FallStateMachine",
    "iou",
    "__version__",
]
