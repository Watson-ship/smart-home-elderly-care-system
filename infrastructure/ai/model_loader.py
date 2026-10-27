"""加载跌倒检测模型权重。

真正的模型封装在项目根目录的 ``fallwatch`` 包里（由原 fall-watch 项目融入），
本文件只做后端友好的适配：

- 默认读取 ``config.settings.AI_MODEL_PATH``（默认 ``model/best.pt``）；
- 相对路径按**项目根目录**解析，不受启动时工作目录影响；
- 延迟 import ``fallwatch`` / ultralytics，避免后端启动时就强制加载 torch；
- 进程内复用同一个 Detector，可用 ``force_reload=True`` 重新加载。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import config.settings as settings

# infrastructure/ai/model_loader.py -> 上三级就是项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_detector = None
_detector_key = None
_lock = threading.Lock()


def resolve_model_path(model_path: Optional[str] = None) -> str:
    """把配置里的模型路径解析成绝对路径。"""
    raw = model_path or settings.AI_MODEL_PATH
    path = Path(raw)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return str(path)


def load_detector(
    model_path: Optional[str] = None,
    *,
    imgsz: Optional[int] = None,
    conf: Optional[float] = None,
    device: str = "cpu",
    force_reload: bool = False,
):
    """加载（或复用）YOLO 检测器，返回 ``fallwatch.detector.Detector``。"""
    global _detector, _detector_key

    path = resolve_model_path(model_path)
    key = (path, imgsz, conf, device)

    with _lock:
        if _detector is not None and _detector_key == key and not force_reload:
            return _detector

        from fallwatch.detector import Detector  # 延迟 import，避免后端启动就加载 torch

        _detector = Detector(
            model_path=path,
            imgsz=imgsz,
            conf=conf,
            device=device,
        )
        _detector_key = key
        return _detector


def get_detector(
    model_path: Optional[str] = None,
    *,
    imgsz: Optional[int] = None,
    conf: Optional[float] = None,
    device: str = "cpu",
):
    """``load_detector`` 的别名，语义上更贴近“取当前检测器”。"""
    return load_detector(model_path, imgsz=imgsz, conf=conf, device=device)


def reset_detector() -> None:
    """释放缓存的检测器（测试或切换模型时用）。"""
    global _detector, _detector_key
    with _lock:
        _detector = None
        _detector_key = None
