"""AI 推理: 输入视频帧, 输出是否跌倒。

底层复用项目根目录 ``fallwatch`` 包的模型与状态机：

- :func:`infer_frame` —— 单帧检测，给出检测框和“本帧是否 falldown”；
  没有时间上下文，适合调试、截图或设备侧上报。
- :class:`FallMonitor` —— 有状态的视频流判定器，内部是
  ``fallwatch.state_machine.FallStateMachine``（滑动窗口 + 多目标跟踪 +
  场景切换 + 冷却），按时间戳逐帧喂入，返回确认后的跌倒事件。

说明：长时间静止（static）不在本模块，属于设备/定时任务侧的判断
（见 ``infrastructure/scheduler/task.py``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List, Optional

from infrastructure.ai import model_loader

if TYPE_CHECKING:  # 仅用于类型标注，避免 import 时就依赖 numpy
    import numpy as np


@dataclass
class FrameInference:
    """单帧推理结果。"""

    is_fall: bool
    fall_conf: float
    detections: List[Any] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)


def infer_frame(frame: "np.ndarray", *, detector=None) -> FrameInference:
    """对单帧做检测，返回是否跌倒及该帧全部检测框。

    参数
    ----
    frame    : OpenCV BGR 图像（numpy.ndarray）。
    detector : 可传入已加载的 Detector 复用，不传则用进程内单例。
    """
    det = detector or model_loader.get_detector()
    detections = det.infer(frame)

    fall_dets = [d for d in detections if det.is_fall(d.cls_name)]
    best = max(fall_dets, key=lambda d: d.conf) if fall_dets else None

    return FrameInference(
        is_fall=best is not None,
        fall_conf=float(best.conf) if best is not None else 0.0,
        detections=detections,
        labels=[d.cls_name for d in detections],
    )


class FallMonitor:
    """按视频流时间戳做有状态跌倒判定。

    典型用法（每来一帧调用一次）::

        monitor = FallMonitor(conf_min=0.5, fall_frames_min=20)
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            result = monitor.process(frame, t)
            for event in result.events:
                # event 是 fallwatch.state_machine.FallEvent
                ...

    参数为 ``None`` 时使用 ``fallwatch.config`` 里的默认阈值。
    """

    def __init__(
        self,
        *,
        model_path: Optional[str] = None,
        detector=None,
        detect_conf: Optional[float] = None,
        device: str = "cpu",
        conf_min: Optional[float] = None,
        window_sec: Optional[float] = None,
        fall_frames_min: Optional[int] = None,
        require_transition: Optional[bool] = None,
        cooldown_sec: Optional[float] = None,
        debounce_frames: Optional[int] = None,
        scene_cut_diff=None,
    ) -> None:
        from fallwatch.state_machine import FallStateMachine

        self.detector = detector or model_loader.load_detector(
            model_path,
            conf=detect_conf,
            device=device,
        )
        kwargs = {
            "conf_min": conf_min,
            "window_sec": window_sec,
            "fall_frames_min": fall_frames_min,
            "require_transition": require_transition,
            "cooldown_sec": cooldown_sec,
            "debounce_frames": debounce_frames,
        }
        if scene_cut_diff is not None:
            kwargs["scene_cut_diff"] = scene_cut_diff
        self.machine = FallStateMachine(**kwargs)
        self._last_detections = []

    def process(self, frame: "np.ndarray", t: float, *, run_inference: bool = True):
        """处理一帧，返回 ``fallwatch.state_machine.FrameResult``。

        ``run_inference=False`` 时复用上一帧检测结果（跳帧推理场景），
        此时不会重复累计窗口。
        """
        if run_inference:
            detections = self.detector.infer(frame)
            self._last_detections = detections
        else:
            detections = self._last_detections
        return self.machine.process(t, frame, detections, run_inference=run_inference)

    def process_detections(self, t: float, detections, frame=None):
        """已有检测结果、只想走状态机时使用。"""
        return self.machine.process(t, frame, detections, run_inference=True)

    @property
    def active_tracks(self) -> int:
        return self.machine.active_tracks

    @property
    def scene_index(self) -> int:
        return self.machine.scene_index
