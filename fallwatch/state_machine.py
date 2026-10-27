"""核心判定逻辑：滑动窗口 + 类别转换 + 轨迹跟踪 + 场景切换 + 冷却。

这是整个项目最容易写错的部分，也是 lyh 那套机制需要改进的地方。

lyh 的做法（rk3588lyh/src/capture_thread.cc）：只按"检测到目标类的帧数"计数，
达到 frame_threshold 累加 success_count，再达到 trigger_count 就上报。
问题在于它不看类别之间的**转换关系**——一个被持续误判成 falldown 的静止物体
（比如坐着的人、躺着的家具）照样会连续累计并触发告警。

本模块的改进：
  1. 除帧数外，还要求窗口内出现过活动类（standing/walking/sitting），
     即存在"由站到倒"的转换（可用 REQUIRE_TRANSITION 关闭）。
  2. 按 IoU 跟踪每个人，各自独立判定，避免多人互相干扰。
  3. 三层冷却：全局冷却、单轨迹冷却、告警后重置。
  4. 场景切换检测，让剪辑合集里的每段独立判定。
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import config
from .detector import Detection

Box = Tuple[int, int, int, int]


# ================================================================ 数据结构


@dataclass
class Observation:
    """某一时刻对某条轨迹的一次观测。"""

    t: float
    cls_name: str
    cls_id: int
    conf: float
    is_fall: bool
    box: Box


@dataclass
class FallEvent:
    """一次确认的跌倒事件。"""

    event_id: str
    t: float  # 事件确认时刻
    first_fall_t: float  # 窗口内首次 falldown 的时刻
    track_id: int
    conf: float  # 窗口内 falldown 的最大置信度
    fall_frames: int
    window_frames: int
    window_span: float
    duration_ms: int
    trace: List[str]
    box: Box
    scene_index: int


@dataclass
class Track:
    """一条轨迹（一个人）。"""

    track_id: int
    observations: Deque[Observation] = field(default_factory=deque)
    last_box: Optional[Box] = None
    last_seen: float = 0.0
    hits: int = 0
    first_seen: float = 0.0
    last_alert_t: float = -1e9
    alerted: bool = False  # 上次告警后是否还没"恢复"
    recent_classes: Deque[str] = field(default_factory=deque)  # 用于多数表决


@dataclass
class FrameResult:
    """一帧的处理结果，交给 cli 决定怎么输出/落日志。"""

    detections: List[Detection]
    events: List[FallEvent]
    active_tracks: int
    scene_cut: bool
    window_snapshot: Dict[int, List[Observation]]


# ================================================================ 工具函数


def iou(a: Box, b: Box) -> float:
    """两个框的交并比。"""

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)

    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = float(iw * ih)
    if inter <= 0:
        return 0.0

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = float(area_a + area_b) - inter
    return inter / union if union > 0 else 0.0


def format_trace(observations: Sequence[Observation], max_items: int = 12) -> List[str]:
    """把观测序列压成类别名列表，用于日志里回溯"当时看到了什么"。"""

    names = [o.cls_name for o in observations]
    if len(names) <= max_items:
        return names
    # 保留头尾，中间折叠
    head = names[: max_items // 2]
    tail = names[-(max_items - len(head) - 1):]
    return head + ["..."] + tail


# ================================================================ 场景切换


class SceneCutDetector:
    """用帧直方图相似度检测硬切。

    合集/剪辑视频（比如"50种摔倒方式"）必须开这个，否则上一段的跌倒状态
    会跨段残留，或者冷却时间把后面几十次跌倒全吃掉。
    """

    def __init__(self, threshold: Optional[float] = None) -> None:
        self.threshold = config.SCENE_CUT_DIFF if threshold is None else threshold
        self._prev_hist: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._prev_hist = None

    def analyze(self, frame: np.ndarray) -> Tuple[bool, float]:
        """返回 (是否场景切换, 相似度)。首帧永远不算切换。"""

        if self.threshold is None or frame is None or frame.size == 0:
            return False, 1.0

        size = config.SCENE_CUT_THUMB
        small = cv2.resize(frame, (size, size), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)

        if self._prev_hist is None:
            self._prev_hist = hist
            return False, 1.0

        similarity = float(cv2.compareHist(self._prev_hist, hist, cv2.HISTCMP_CORREL))
        self._prev_hist = hist

        return similarity < self.threshold, similarity


# ================================================================ 状态机


class FallStateMachine:
    """把逐帧检测结果判定成跌倒事件。"""

    def __init__(
        self,
        *,
        conf_min: float = None,
        window_sec: float = None,
        fall_frames_min: int = None,
        require_transition: bool = None,
        cooldown_sec: float = None,
        per_track_cooldown_sec: float = None,
        per_track_reset_frames: int = None,
        iou_threshold: float = None,
        track_ttl_sec: float = None,
        track_min_hits: int = None,
        debounce_frames: int = None,
        scene_cut_diff=config.SCENE_CUT_DIFF,
        scene_blank_sec: float = None,
    ) -> None:
        self.conf_min = config.CONF_MIN if conf_min is None else conf_min
        self.window_sec = config.WINDOW_SEC if window_sec is None else window_sec
        self.fall_frames_min = (
            config.FALL_FRAMES_MIN if fall_frames_min is None else fall_frames_min
        )
        self.require_transition = (
            config.REQUIRE_TRANSITION if require_transition is None else require_transition
        )
        self.cooldown_sec = config.COOLDOWN_SEC if cooldown_sec is None else cooldown_sec
        self.per_track_cooldown_sec = (
            config.PER_TRACK_ALERT_COOLDOWN_SEC
            if per_track_cooldown_sec is None
            else per_track_cooldown_sec
        )
        self.per_track_reset_frames = (
            config.PER_TRACK_RESET_FRAMES
            if per_track_reset_frames is None
            else per_track_reset_frames
        )
        self.iou_threshold = (
            config.IOU_MATCH_THRESHOLD if iou_threshold is None else iou_threshold
        )
        self.track_ttl_sec = config.TRACK_TTL_SEC if track_ttl_sec is None else track_ttl_sec
        self.track_min_hits = config.TRACK_MIN_HITS if track_min_hits is None else track_min_hits
        self.debounce_frames = max(
            1, int(config.DEBOUNCE_FRAMES if debounce_frames is None else debounce_frames)
        )
        self.scene_blank_sec = (
            config.SCENE_CUT_BLANK_SEC if scene_blank_sec is None else scene_blank_sec
        )

        self.scene = SceneCutDetector(scene_cut_diff)

        self._tracks: Dict[int, Track] = {}
        self._next_track_id = 1
        self._last_alert_t = -1e9
        self._scene_index = 0
        self._blank_until = -1e9
        self._event_counter = 0

    # ------------------------------------------------------------ 对外状态

    @property
    def active_tracks(self) -> int:
        return len(self._tracks)

    @property
    def scene_index(self) -> int:
        return self._scene_index

    # ------------------------------------------------------------ 主入口

    def process(
        self,
        t: float,
        frame: Optional[np.ndarray],
        detections: Sequence[Detection],
        *,
        run_inference: bool = True,
    ) -> FrameResult:
        """处理一帧。

        参数
        ----
        t            : 该帧的时间戳（秒，单调递增）
        frame        : 原始帧；仅用于场景切换检测与抓拍，可为 None
        detections   : 该帧的检测结果；run_inference=False 时应传上一帧的结果
        run_inference: 本帧是否真的做了推理。跳帧复用旧结果时传 False，
                       此时不更新窗口（避免把同一帧重复计数）。
        """

        scene_cut = False

        if frame is not None:
            scene_cut, _ = self.scene.analyze(frame)
            if scene_cut:
                self._on_scene_cut(t)

        if t < self._blank_until:
            # 场景切换瞬间的糊帧，直接忽略
            return FrameResult([], [], len(self._tracks), scene_cut, {})

        if not run_inference:
            return FrameResult(list(detections), [], len(self._tracks), scene_cut, {})

        self._update_tracks(t, detections)
        self._prune_tracks(t)

        events = self._evaluate(t)

        snapshot = {
            tid: list(tr.observations)
            for tid, tr in self._tracks.items()
            if tr.observations
        }

        return FrameResult(
            detections=list(detections),
            events=events,
            active_tracks=len(self._tracks),
            scene_cut=scene_cut,
            window_snapshot=snapshot,
        )

    # ------------------------------------------------------------ 内部：场景

    def _on_scene_cut(self, t: float) -> None:
        self._scene_index += 1
        self._tracks.clear()
        self._last_alert_t = -1e9
        self._blank_until = t + self.scene_blank_sec
        self.scene.reset()

    # ------------------------------------------------------------ 内部：跟踪

    def _update_tracks(self, t: float, detections: Sequence[Detection]) -> None:
        unmatched_tracks = set(self._tracks.keys())
        matched_pairs: List[Tuple[int, Detection]] = []

        # 贪心匹配：检测已按置信度降序，所以优先满足高置信度框
        for det in detections:
            best_tid = None
            best_iou = self.iou_threshold
            for tid in unmatched_tracks:
                track = self._tracks[tid]
                if track.last_box is None:
                    continue
                score = iou(track.last_box, det.box)
                if score > best_iou:
                    best_iou = score
                    best_tid = tid
            if best_tid is not None:
                unmatched_tracks.discard(best_tid)
                matched_pairs.append((best_tid, det))

        # 更新已匹配的轨迹
        for tid, det in matched_pairs:
            self._append_observation(self._tracks[tid], t, det)

        # 未匹配的检测 -> 新建轨迹
        matched_dets = {id(d) for _, d in matched_pairs}
        for det in detections:
            if id(det) in matched_dets:
                continue
            track = Track(
                track_id=self._next_track_id,
                last_box=det.box,
                last_seen=t,
                first_seen=t,
                hits=1,
            )
            self._append_observation(track, t, det)
            self._tracks[track.track_id] = track
            self._next_track_id += 1

    def _append_observation(self, track: Track, t: float, det: Detection) -> None:
        # 先更新多数表决缓冲，再用表决结果作为该帧的有效类别。
        # 这样单帧的类别抖动不会立刻改变判定状态。
        track.recent_classes.append(det.cls_name)
        while len(track.recent_classes) > self.debounce_frames:
            track.recent_classes.popleft()

        effective_name = det.cls_name
        if self.debounce_frames > 1 and track.recent_classes:
            effective_name = Counter(track.recent_classes).most_common(1)[0][0]

        is_fall = effective_name.lower() in config.FALL_CLASS_NAMES
        track.observations.append(
            Observation(
                t=t,
                cls_name=effective_name,
                cls_id=det.cls_id,
                conf=det.conf,
                is_fall=is_fall,
                box=det.box,
            )
        )
        track.last_box = det.box
        track.last_seen = t
        track.hits += 1

        # 只保留窗口时长内的观测
        cutoff = t - self.window_sec
        while track.observations and track.observations[0].t < cutoff:
            track.observations.popleft()

        # 告警后重置：连续足够多帧不再是 falldown，则允许再次告警
        if track.alerted and not is_fall:
            tail = list(track.observations)[-self.per_track_reset_frames:]
            if len(tail) >= self.per_track_reset_frames and not any(o.is_fall for o in tail):
                track.alerted = False

    def _prune_tracks(self, t: float) -> None:
        dead = [tid for tid, tr in self._tracks.items() if t - tr.last_seen > self.track_ttl_sec]
        for tid in dead:
            self._tracks.pop(tid, None)

    # ------------------------------------------------------------ 内部：判定

    def _evaluate(self, t: float) -> List[FallEvent]:
        events: List[FallEvent] = []

        for track in self._tracks.values():
            obs = list(track.observations)
            if not obs:
                continue

            # 轨迹刚建立、样本太少 -> 不判定，避免噪声框造事件
            if track.hits < self.track_min_hits:
                continue

            fall_obs = [o for o in obs if o.is_fall]
            if not fall_obs:
                continue

            # 条件 1：窗口内 falldown 观测数达标
            if len(fall_obs) < self.fall_frames_min:
                continue

            # 条件 2：置信度门槛
            max_conf = max(o.conf for o in fall_obs)
            if max_conf < self.conf_min:
                continue

            # 条件 3：必须存在"由站到倒"的转换（可关闭）
            #
            # 判据放宽为两种任一成立：
            #   a) 在最后一次 falldown 观测之前出现过活动类 —— 典型的由站到倒；
            #   b) 窗口内同时存在活动类和 falldown 类，且 falldown 已占多数 ——
            #      应对"缓慢倒下、类别来回抖动"的情况。
            # 这样既保留了对静止物体被误判成 falldown 的抑制（那种情况窗口里
            # 一个活动类都不会有），又不会像"必须在首次 falldown 之前出现活动类"
            # 那样，把从跌倒中途开始的片段全部漏掉。
            if self.require_transition:
                last_fall_t = fall_obs[-1].t
                activity_obs = [o for o in obs if not o.is_fall]

                case_a = any(o.t <= last_fall_t for o in activity_obs)
                case_b = bool(activity_obs) and len(fall_obs) >= max(
                    self.fall_frames_min, len(activity_obs)
                )

                if not (case_a or case_b):
                    continue

            # 条件 4：三层冷却
            if t - self._last_alert_t < self.cooldown_sec:
                continue
            if t - track.last_alert_t < self.per_track_cooldown_sec:
                continue
            if track.alerted:
                continue

            # 全部满足 -> 确认一次跌倒
            event = self._make_event(track, obs, fall_obs, t, max_conf)
            events.append(event)

            self._last_alert_t = t
            track.last_alert_t = t
            track.alerted = True

            # 清空窗口，让该轨迹重新累计
            track.observations.clear()

        return events

    def _make_event(
        self,
        track: Track,
        obs: List[Observation],
        fall_obs: List[Observation],
        t: float,
        max_conf: float,
    ) -> FallEvent:
        self._event_counter += 1
        first_fall_t = fall_obs[0].t
        last_fall_t = fall_obs[-1].t

        return FallEvent(
            event_id=f"E{self._event_counter:05d}",
            t=t,
            first_fall_t=first_fall_t,
            track_id=track.track_id,
            conf=max_conf,
            fall_frames=len(fall_obs),
            window_frames=len(obs),
            window_span=obs[-1].t - obs[0].t,
            duration_ms=int(max(0.0, last_fall_t - first_fall_t) * 1000),
            trace=format_trace(obs),
            box=fall_obs[-1].box,
            scene_index=self._scene_index,
        )
