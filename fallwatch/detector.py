"""模型加载与推理封装。

设计目标：把"模型相关"的所有不确定性收在这一个文件里，对外只吐统一结构：

    [{"box": (x1, y1, x2, y2), "cls_id": int, "cls_name": str, "conf": float}, ...]

这样 state_machine / logger / cli 都与模型无关。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import config


@dataclass
class Detection:
    """一条检测结果。"""

    box: Tuple[int, int, int, int]  # x1, y1, x2, y2
    cls_id: int
    cls_name: str
    conf: float

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.box
        return max(0, x2 - x1) * max(0, y2 - y1)

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _patch_torch_load() -> None:
    """让旧版 ultralytics 权重能在 torch>=2.6 上加载。

    torch 2.6 起 torch.load 默认 weights_only=True，加载旧 .pt 会报
    "Weights only load failed"。这里把 ultralytics 的模型类注册进安全列表，
    从而不需要降级 ultralytics。
    """

    try:
        import torch
    except Exception:
        return

    candidates = [
        ("ultralytics.nn.tasks", "DetectionModel"),
        ("ultralytics.nn.tasks", "SegmentationModel"),
        ("ultralytics.nn.tasks", "ClassificationModel"),
        ("ultralytics.nn.tasks", "PoseModel"),
        ("ultralytics.nn.modules", "Conv"),
        ("ultralytics.nn.modules", "C2f"),
        ("ultralytics.nn.modules", "SPPF"),
        ("ultralytics.nn.modules", "Bottleneck"),
        ("ultralytics.nn.modules.block", "C2f"),
        ("ultralytics.nn.modules.block", "Bottleneck"),
        ("ultralytics.nn.modules.block", "SPPF"),
        ("ultralytics.nn.modules.conv", "Conv"),
        ("ultralytics.nn.modules.head", "Detect"),
    ]

    import importlib

    globals_list = []
    for module_name, attr in candidates:
        try:
            mod = importlib.import_module(module_name)
            obj = getattr(mod, attr, None)
            if obj is not None:
                globals_list.append(obj)
        except Exception:
            continue

    if not globals_list:
        return

    try:
        torch.serialization.add_safe_globals(globals_list)
    except Exception:
        # 老版本 torch 没有 add_safe_globals，忽略即可
        pass

    # 同时放宽 weights_only，双保险
    try:
        original_load = torch.load

        def _patched_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return original_load(*args, **kwargs)

        torch.load = _patched_load  # type: ignore[assignment]
    except Exception:
        pass


class Detector:
    """YOLOv8 检测器（CPU 可跑，无需专用硬件）。"""

    def __init__(
        self,
        model_path: str = None,
        imgsz: int = None,
        conf: float = None,
        device: str = "cpu",
    ) -> None:
        self.model_path = model_path or config.DEFAULT_MODEL
        self.imgsz = int(imgsz or config.IMGSZ)
        self.conf = float(config.DETECT_CONF if conf is None else conf)
        self.device = device

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"找不到模型文件: {self.model_path}\n"
                "请从 lyh 仓库获取 best.pt，放到 model/ 目录。\n"
                "下载地址见 README.md 的『从 lyh 拿什么』一节，"
                "或直接运行: python tools/fetch_model.py --print-url"
            )

        _patch_torch_load()

        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "未安装 ultralytics。请执行: pip install -r requirements.txt"
            ) from exc

        self.model = YOLO(self.model_path)

        names = getattr(self.model, "names", None) or {}
        if isinstance(names, (list, tuple)):
            self.names = {i: str(n) for i, n in enumerate(names)}
        else:
            self.names = {int(k): str(v) for k, v in dict(names).items()}

        self._warn_if_unexpected_classes()

    # ------------------------------------------------------------ 自检

    def _warn_if_unexpected_classes(self) -> None:
        found = {n.lower() for n in self.names.values()}
        if not found & config.FALL_CLASS_NAMES:
            print(
                "[警告] 模型类别里没有找到跌倒类，实际类别为: "
                f"{sorted(self.names.values())}\n"
                "        请检查 config.FALL_CLASS_NAMES 是否与模型匹配。"
            )

    def is_fall(self, name: str) -> bool:
        return name.lower() in config.FALL_CLASS_NAMES

    def is_activity(self, name: str) -> bool:
        return name.lower() in config.ACTIVITY_CLASS_NAMES

    # ------------------------------------------------------------ 推理

    def infer(self, frame: np.ndarray) -> List[Detection]:
        """对一帧做推理，返回归一化后的检测列表（已按面积过滤）。"""

        if frame is None or frame.size == 0:
            return []

        results = self.model.predict(
            source=frame,
            imgsz=self.imgsz,
            conf=self.conf,
            device=self.device,
            verbose=False,
        )
        if not results:
            return []

        r = results[0]
        boxes = getattr(r, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        h, w = frame.shape[:2]
        frame_area = float(h * w) or 1.0
        min_area = config.MIN_BOX_AREA_RATIO * frame_area

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy().astype(int)

        detections: List[Detection] = []
        for (x1, y1, x2, y2), c, cid in zip(xyxy, confs, clss):
            box = (int(x1), int(y1), int(x2), int(y2))
            det = Detection(
                box=box,
                cls_id=int(cid),
                cls_name=self.names.get(int(cid), str(cid)),
                conf=float(c),
            )
            if det.area < min_area:
                continue
            detections.append(det)

        # 置信度从高到低，后续 IoU 匹配按此顺序贪心
        detections.sort(key=lambda d: d.conf, reverse=True)
        return detections

    # ------------------------------------------------------------ 绘制

    def draw(self, frame: np.ndarray, detections: Sequence[Detection]) -> np.ndarray:
        """在帧上画出检测框。就地修改并返回。"""

        if not config.DRAW_BOXES:
            return frame

        for det in detections:
            x1, y1, x2, y2 = det.box
            if self.is_fall(det.cls_name):
                color = config.COLOR_FALL
            elif self.is_activity(det.cls_name):
                color = config.COLOR_ACTIVITY
            else:
                color = config.COLOR_OTHER

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            label = f"{det.cls_name} {det.conf:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            ty = max(y1 - 6, th + 4)
            cv2.rectangle(frame, (x1, ty - th - 4), (x1 + tw + 4, ty + 2), color, -1)
            cv2.putText(
                frame,
                label,
                (x1 + 2, ty - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )

        return frame


def summarize_frame(detections: Sequence[Detection]) -> str:
    """把一帧的检测结果压成一行，给 dry-run / 调试用。"""

    if not detections:
        return "(无检测)"
    return ", ".join(f"{d.cls_name}:{d.conf:.2f}" for d in detections)
