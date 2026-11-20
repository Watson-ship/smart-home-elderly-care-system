"""实时画面帧中转(内存), 供 MJPEG 推流使用。

为什么要单独一层:
    阶段 1/2 的 /api/device/stream 是"跌倒截图"语义(落盘 + 建 alert),
    阶段 3 的实时画面每 2 秒来一帧, 如果也走 /stream 就会每 2 秒建一条告警。
    所以实时画面单独走 /api/device/frame -> 只把**最新一帧**留在内存里,
    家属端用 <img src="/api/device/live/{sn}"> 就能看到"动起来"的画面。

为什么放内存不放磁盘:
    实时画面只在"有人正在看"的那一刻有意义, 落盘既浪费空间又会把 static/ 撑爆。
    这里每台设备只保留最后 1 帧(几十 KB), 断流超过 LIVE_IDLE_TIMEOUT 秒自动失效。

线程安全:
    publish 由 FastAPI 的工作线程调用, mjpeg_chunks 由 shove 线程调用,
    两边都操作同一台设备的帧, 所以统一用一把锁。

依赖: 只用标准库, 不引入额外包。
"""
import threading
import time
from typing import Iterator, Optional, Tuple

# 超过这个秒数没有新帧, 就认为设备断流了(MJPEG 连接会自动结束, 浏览器显示占位)
LIVE_IDLE_TIMEOUT = 15.0

# MJPEG 的 multipart 分隔符, 客户端(浏览器)靠它切分每一帧
BOUNDARY = "frame"

_lock = threading.Lock()
# device_sn -> (jpeg 字节, 收到该帧的 monotonic 时间)
_latest: dict[str, Tuple[bytes, float]] = {}
# device_sn -> 正在看的人数(仅用于返回给前端展示/排查)
_viewers: dict[str, int] = {}


def publish(device_sn: str, jpeg: bytes) -> None:
    """设备推来一帧, 覆盖旧的。frame 端点专用, 不会建告警。"""
    with _lock:
        _latest[device_sn] = (jpeg, time.monotonic())


def latest(device_sn: str) -> Optional[Tuple[bytes, float]]:
    """取最新一帧 (jpeg, 收到时间); 没有或已过期返回 None。

    过期就顺手把这一帧从字典里删掉: 否则设备下线后, 那几十 KB 的 jpeg
    会一直挂在内存里, 设备越多泄漏越多(每台一份)。
    """
    with _lock:
        item = _latest.get(device_sn)
        if item is None:
            return None
        if time.monotonic() - item[1] > LIVE_IDLE_TIMEOUT:
            _latest.pop(device_sn, None)
            return None
        return item


def viewer_count(device_sn: str) -> int:
    """当前正在观看这台设备的人数。"""
    with _lock:
        return _viewers.get(device_sn, 0)


def clear(device_sn: str) -> None:
    """丢弃某台设备的帧(设备下线/测试收尾用)。"""
    with _lock:
        _latest.pop(device_sn, None)


def active_devices() -> list[str]:
    """当前有实时帧的设备列表(排查用), 顺手清掉已过期的。"""
    now = time.monotonic()
    with _lock:
        expired = [sn for sn, (_, ts) in _latest.items() if now - ts > LIVE_IDLE_TIMEOUT]
        for sn in expired:
            _latest.pop(sn, None)
        return list(_latest.keys())


def _part(jpeg: bytes) -> bytes:
    """按 multipart/x-mixed-replace 格式包一帧。"""
    return (
        f"--{BOUNDARY}\r\n"
        f"Content-Type: image/jpeg\r\n"
        f"Content-Length: {len(jpeg)}\r\n\r\n"
    ).encode("ascii") + jpeg + b"\r\n"


def mjpeg_chunks(device_sn: str, fps: float = 10.0) -> Iterator[bytes]:
    """MJPEG 生成器: 有新帧就推, 没新帧就重复最后一帧(保持画面不闪)。

    结束条件:
        - 断流超过 LIVE_IDLE_TIMEOUT 秒(摄像端挂了/停了), 自动结束连接;
        - 浏览器关闭连接时, Starlette 会停止迭代。
    """
    frame_interval = 1.0 / max(fps, 1.0)
    last_ts = -1.0
    with _lock:
        _viewers[device_sn] = _viewers.get(device_sn, 0) + 1
    try:
        while True:
            item = latest(device_sn)
            if item is None:
                # 一开始就没帧 / 中途断流: 结束, 前端 <img> 自然显示裂图或占位
                return
            jpeg, ts = item
            if ts != last_ts:
                last_ts = ts
                yield _part(jpeg)
            time.sleep(frame_interval)
    finally:
        with _lock:
            remain = _viewers.get(device_sn, 1) - 1
            if remain > 0:
                _viewers[device_sn] = remain
            else:
                _viewers.pop(device_sn, None)
