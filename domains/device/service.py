"""摄像头设备业务逻辑。

Owner 划分:
    Person A (硬件方向): register_device / heartbeat / verify_device / save_video /
                        save_fall_screenshot
    Person B (家属方向): 绑定后的查询、解绑等, 追加在下方并注明 Owner

说明: 摄像头是机器, 用 device_sn 认身份, 所以这几个接口不需要登录。
      设备必须先手动注册 (register_device), 心跳才能刷新在线状态。

职责边界: 跌倒判定在**摄像端**完成 (摄像端调用 infrastructure/ai/inference.py)。
          摄像端只把确认跌倒的那一帧截图传上来, 后端负责存图 + 生成 alert 记录;
          持续录制的视频片段作为录像证据另行上传 (save_video)。
"""
from datetime import datetime
from pathlib import Path
import queue
import threading

from sqlalchemy.orm import Session

from models import Alert, Device, Elder

# 设备上传的视频片段保存目录 (运行时自动创建, 已在 .gitignore 中忽略)
VIDEO_DIR = Path("static") / "videos"

# 摄像端上报的跌倒截图保存目录
STREAM_DIR = Path("static") / "stream"

# 允许的录像扩展名
VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv"}

# 允许的截图扩展名
STREAM_SUFFIXES = {".jpg", ".jpeg", ".png"}


def verify_device(db: Session, device_sn: str) -> Device | None:
    """按序列号查设备, 查不到返回 None。"""
    return db.query(Device).filter(Device.device_sn == device_sn).first()


def register_device(db: Session, device_sn: str, device_name: str) -> Device:
    """手动注册设备: 先登记 SN 和设备名, 设备之后才能接入。

    与自动注册的区别: 只有登记过的 SN 才允许心跳和上传画面,
    避免任何陌生设备随意写入数据库。注册后状态为 offline,
    等设备第一次心跳成功才会变成 online。
    """
    if verify_device(db, device_sn) is not None:
        raise ValueError(f"设备 {device_sn} 已注册, 无需重复注册")

    device = Device(
        device_sn=device_sn,
        device_name=device_name,
        status="offline",
        last_online_time=None,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def heartbeat(db: Session, device_sn: str) -> Device:
    """处理设备心跳。

    只接受已手动注册的设备: 未注册时抛 LookupError, 由路由层转成 404。
    注册过的设备刷新 last_online_time 并把状态改回 online。
    """
    device = verify_device(db, device_sn)
    if device is None:
        raise LookupError(f"设备 {device_sn} 未注册, 请先调用 POST /api/device/register")

    device.status = "online"
    device.last_online_time = datetime.now()
    db.commit()
    db.refresh(device)
    return device


def save_video(db: Session, device_sn: str, video_bytes: bytes, suffix: str = ".mp4") -> Path:
    """保存设备上传的一段视频到 static/videos/{device_sn}/{时间戳}.mp4。

    每段视频单独存一个文件, 不覆盖: 时间戳精确到毫秒, 同一设备连续上传也不会撞名。
    AI 模块 (Person C) 之后从 VIDEO_DIR 里取文件做摔倒检测, 并自己截图存告警图。
    设备未注册时抛 LookupError (必须先调 /register 手动注册)。
    """
    if verify_device(db, device_sn) is None:
        raise LookupError(f"设备 {device_sn} 未注册, 请先调用 POST /api/device/register")

    # 目录名只保留字母/数字/下划线/短横线, 防止 ../ 之类的路径穿越
    safe_sn = "".join(ch for ch in device_sn if ch.isalnum() or ch in "-_")
    if not safe_sn:
        raise ValueError("设备序列号不合法")

    # 扩展名白名单, 防止上传 .exe 之类的文件
    if suffix not in VIDEO_SUFFIXES:
        suffix = ".mp4"

    device_dir = VIDEO_DIR / safe_sn
    device_dir.mkdir(parents=True, exist_ok=True)

    # 精确到毫秒的时间戳, 保证同一设备的每段视频都有唯一文件名
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    target = device_dir / f"{stamp}{suffix}"
    target.write_bytes(video_bytes)
    return target


def find_latest_video(db: Session, device_sn: str) -> Path:
    """找该设备最新上传的一段视频 (/detect/latest 用, 免得把同一个文件再传一遍)。

    设备未注册抛 LookupError; 目录里没有视频抛 ValueError。
    """
    if verify_device(db, device_sn) is None:
        raise LookupError(f"设备 {device_sn} 未注册, 请先调用 POST /api/device/register")

    safe_sn = "".join(ch for ch in device_sn if ch.isalnum() or ch in "-_")
    if not safe_sn:
        raise ValueError("设备序列号不合法")

    device_dir = VIDEO_DIR / safe_sn
    files = (
        [p for p in device_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES]
        if device_dir.is_dir()
        else []
    )
    if not files:
        raise ValueError(f"设备 {device_sn} 还没有上传过视频, 请先调 POST /api/device/video")
    return max(files, key=lambda p: p.stat().st_mtime)


def save_fall_screenshot(
    db: Session,
    device_sn: str,
    image_bytes: bytes,
    suffix: str = ".jpg",
    name_tag: str | None = None,
) -> tuple[Path, Alert | None]:
    """保存摄像端判定为跌倒后上传的截图, 并生成一条 fall 告警记录。

    与 save_video 的区别: 视频是"一直在录、按时切段"的普通录像证据;
    本函数只在摄像端 AI 确认跌倒时被调用, 所以一张图对应一次告警。

    截图存到 static/stream/{device_sn}/{毫秒时间戳}[_tag].jpg, 每次告警单独一个文件,
    不会互相覆盖。name_tag 用于离线检测时标出"视频第几毫秒"的跌倒帧,
    例如 name_tag='t12000' -> 20261103_101500_123_t12000.jpg。

    告警记录: 设备已绑定老人时写一条 alert (alert_type='fall',
    screenshot_path 为相对 static 的路径, 与 seed 数据保持一致);
    设备还没绑定老人时只存图不写告警, 返回值里 alert 为 None。

    设备未注册抛 LookupError, 序列号/扩展名不合法抛 ValueError。
    """
    device = verify_device(db, device_sn)
    if device is None:
        raise LookupError(f"设备 {device_sn} 未注册, 请先调用 POST /api/device/register")

    safe_sn = "".join(ch for ch in device_sn if ch.isalnum() or ch in "-_")
    if not safe_sn:
        raise ValueError("设备序列号不合法")

    if suffix not in STREAM_SUFFIXES:
        suffix = ".jpg"

    device_dir = STREAM_DIR / safe_sn
    device_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    tag = f"_{name_tag}" if name_tag else ""
    filename = f"{stamp}{tag}{suffix}"
    target = device_dir / filename
    target.write_bytes(image_bytes)

    alert = None
    if device.elder_id is not None:
        alert = Alert(
            elder_id=device.elder_id,
            device_id=device.id,
            alert_type="fall",
            # 相对 static 的路径, 前端拼成 /static/{screenshot_path} 即可访问
            screenshot_path=(Path("stream") / safe_sn / filename).as_posix(),
            is_handled=0,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

    return target, alert


def _encode_frame_with_boxes(frame, detections, detector, quality: int = 85) -> bytes | None:
    """把一帧(画上检测框)编码成 jpg 字节。"""
    import cv2  # 延迟 import: 只有 AI 相关接口才需要 opencv

    img = frame.copy()
    try:
        detector.draw(img, detections)
    except Exception:
        pass  # 画框失败不影响截图本身
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def detect_falls_in_video(
    db: Session,
    device_sn: str,
    video_path: Path | str,
    infer_every: int = 3,
    max_frames: int = 900,
    require_transition: bool | None = None,
    conf_min: float | None = None,
    cooldown_sec: float | None = 5.0,
    per_track_cooldown_sec: float | None = 5.0,
    per_track_reset_frames: int | None = None,
) -> dict:
    """对上传的视频文件做离线跌倒检测, 并把每个跌倒帧截图存下来。

    与摄像端实时判定的区别: 这是**事后**跑一遍视频(联调/验收用),
    不用摄像头也能验证"能不能截到摔倒那一帧"。

    流程:
        逐帧读视频 -> 每 infer_every 帧真的推理一次(其余帧复用上一次结果)
        -> 交给 FallMonitor 的有状态判定(滑动窗口 3s + 多目标跟踪 + 冷却)
        -> 确认跌倒时, 把当前帧画上框存成 jpg 并生成 alert

    参数:
        infer_every      : 每 N 帧推理一次。离线检测建议 2~3, 1 最准但最慢。
        max_frames       : 最多处理多少帧(<=0 表示整段视频), 防止长视频把接口拖死。
        require_transition: 是否要求窗口内出现"由站到倒"的转换(默认 True, 误报少但
                           视频一开头就是躺着的片段会漏报)。素材不确定时传 False。
        conf_min         : falldown 置信度门槛, 默认 0.45。
        cooldown_sec     : 全局冷却(秒), 默认 5。**默认 30 会把一段视频里 30 秒内的
                           第二次跌倒吞掉**, 所以离线检测默认调小, 每次跌倒都能截到。
        per_track_cooldown_sec: 同一个人两次告警的最小间隔(秒), 默认 5(配置里是 20)。
        per_track_reset_frames: 告警后连续多少帧不是 falldown 才允许再次告警, 默认用配置(10)。

    返回 dict: frames_processed / fps / infer_every / fall_events / screenshots。

    设备未注册抛 LookupError; 视频打不开抛 ValueError; 模型加载失败抛 RuntimeError。
    """
    import cv2  # 延迟 import

    if infer_every < 1:
        raise ValueError("infer_every 必须 >= 1")

    device = verify_device(db, device_sn)
    if device is None:
        raise LookupError(f"设备 {device_sn} 未注册, 请先调用 POST /api/device/register")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("视频打不开, 请确认是常见的 mp4/avi/mov 文件且没有损坏")

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if not fps or fps <= 1 or fps > 240:
            fps = 25.0  # 有些容器读不到帧率, 退化成常见值

        from infrastructure.ai.inference import FallMonitor  # 延迟 import, 避免启动就加载 torch

        try:
            monitor = FallMonitor(  # 模型是进程内单例, 第二次调用很快
                require_transition=require_transition,
                conf_min=conf_min,
                cooldown_sec=cooldown_sec,
                per_track_cooldown_sec=per_track_cooldown_sec,
                per_track_reset_frames=per_track_reset_frames,
            )
        except Exception as exc:
            raise RuntimeError(f"AI 模型加载失败: {exc}") from exc

        frames_processed = 0
        screenshots: list[dict] = []

        while max_frames <= 0 or frames_processed < max_frames:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            frames_processed += 1

            # 时间戳用"帧号 / fps", 和录像里的真实时间一致, 与摄像头实时模式区分开
            t = frames_processed / fps
            run_inference = infer_every <= 1 or (frames_processed % infer_every == 1)

            result = monitor.process(frame, t, run_inference=run_inference)

            for event in result.events:
                jpg = _encode_frame_with_boxes(frame, result.detections, monitor.detector)
                item = {
                    "event_id": event.event_id,
                    "frame_index": frames_processed,
                    "time_ms": int(round(t * 1000)),
                    "conf": round(float(event.conf), 3),
                    "box": list(event.box),
                    "file_path": None,
                    "file_url": None,
                    "alert_id": None,
                }
                if jpg is not None:
                    saved, alert = save_fall_screenshot(
                        db,
                        device_sn,
                        jpg,
                        ".jpg",
                        name_tag=f"t{item['time_ms']}",
                    )
                    item["file_path"] = saved.as_posix()
                    item["file_url"] = f"/{saved.as_posix()}"
                    item["alert_id"] = alert.id if alert is not None else None
                screenshots.append(item)

        return {
            "device_sn": device_sn,
            "frames_processed": frames_processed,
            "fps": round(fps, 2),
            "infer_every": infer_every,
            "fall_events": len(screenshots),
            "screenshots": screenshots,
        }
    finally:
        cap.release()


# ---------------------------------------------------------------- 后台检测队列

# 摄像端每 10 秒就传来一段视频。如果每段都单独起一个线程跑 AI, 多段同时推理
# 会把 CPU 抢光(录制定时器都跟不上)。这里用"单线程 + 队列"串行处理:
# 上传接口立刻返回, 检测在后台按上传顺序一段一段做。
_detect_queue: "queue.Queue[tuple[str, Path]]" = queue.Queue(maxsize=50)
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


def enqueue_video_detection(device_sn: str, video_path: Path) -> bool:
    """把一段视频排进后台检测队列, 返回是否排队成功。

    队列满(50 段都还没处理完)时返回 False, 调用方可以提示"检测积压, 稍后再传"。
    真正的检测在 _detect_worker 里串行执行。
    """
    global _worker_thread

    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(
                target=_detect_worker, name="fall-detect-worker", daemon=True
            )
            _worker_thread.start()

    try:
        _detect_queue.put_nowait((device_sn, Path(video_path)))
        return True
    except queue.Full:
        return False


def _detect_worker() -> None:
    """队列消费者: 串行跑检测。

    后台线程里没有请求的 session, 每段视频自己开一个数据库会话;
    任何异常都只打印、不往外抛, 否则整个 worker 线程会死掉。
    """
    from db import session as dbs

    while True:
        device_sn, video = _detect_queue.get()
        session = dbs.SessionLocal()
        try:
            result = detect_falls_in_video(session, device_sn, video)
            print(
                f"[自动检测] device={device_sn} video={video.name} "
                f"frames={result['frames_processed']} events={result['fall_events']}"
            )
            for item in result["screenshots"]:
                print(
                    f"[自动检测] 跌倒截图 t={item['time_ms']}ms conf={item['conf']} "
                    f"-> {item['file_path']} (alert_id={item['alert_id']})"
                )
        except Exception as exc:  # noqa: BLE001 后台任务不能把线程搞崩
            print(f"[自动检测失败] device={device_sn} video={video.name}: {exc}")
        finally:
            session.close()
            _detect_queue.task_done()


def bind_device(db: Session, device_sn: str, elder_id: int) -> Device:
    """把设备和老人绑定 (更新 device.elder_id)。

    设备和老人都不存在时抛 LookupError, 由路由层转成 404。
    """
    device = verify_device(db, device_sn)
    if device is None:
        raise LookupError(f"设备 {device_sn} 不存在, 请先让设备上报一次心跳")

    if db.get(Elder, elder_id) is None:
        raise LookupError(f"老人 {elder_id} 不存在")

    device.elder_id = elder_id
    db.commit()
    db.refresh(device)
    return device
