"""本机摄像头联调客户端 (Person A 硬件方向)。

模拟真实摄像头在**设备端**完成的三件事:

1. 连续录制实时画面, 按时间切成一段段视频 (默认只存本机, 循环覆盖)
2. 边录边跑跌倒检测 (复用 infrastructure/ai/inference.py 的 FallMonitor)
   → 只有确认跌倒的那一刻, 才把当前帧截图上传 (/api/device/stream)
   → 后端存图并生成 alert 告警记录, 家属/社康端就能看到
3. 跌倒事件触发后, **自动拼出完整的证据视频** (摔倒前 + 摔倒后, 共约 15 秒)
   → 不管跌倒发生在分段的第几秒, 证据视频里一定包含摔倒全过程

证据视频的拼接原理 (小白版):
    脑子里始终存着最近 --pre-seconds (默认 8) 秒的画面 (像行车记录仪的预录缓存)。
    AI 检测到跌倒的那一刻, 立刻把这 8 秒写下来, 然后再继续录 --post-seconds (默认 7) 秒,
    合起来约 15 秒, 摔倒点就在视频中间偏左的位置, 前后都有画面。

    时间轴示例 (pre=8, post=7, 摔倒发生在第 3.2 秒):
      ┌─────────── 拼出来的证据视频 (15 秒) ──────────┐
      │ 内存里的 8 秒 (摔倒前: 老人还在走)              │ 继续录的 7 秒 (摔倒后)          │
      └────────────────────────────────────────────────────────────────────────────────┘
                                     ↑
                              摔倒点在这里, 前后都有

两种录像策略 (--video-mode):
    local (默认)  录像写进本机 recordings/{sn}/, 只保留最近 --keep-hours 小时(默认 1),
                  旧文件自动删除(像行车记录仪循环覆盖); **只有跌倒触发的证据视频**
                  才上传到服务器。平时不占网络、不占服务器磁盘。
                  好处: 就算 AI 漏判了, 本机这一个小时的录像还在, 事后能人工翻看。
    full          每 --segment-seconds 秒都上传一段(调试/演示用, 一天约 8GB)。

线程分工 (重要):
    录制线程(主线程)  读帧 → 写分段 + 填预缓冲 → 心跳 → 上传跌倒证据, 严格按 --fps 走, 不被 AI 拖慢
    判定线程          从队列里取"抽样的帧" → 跑模型 → 有跌倒事件就截图上传, 并通知主线程
    队列只留 1 帧     AI 跟不上时就丢掉旧帧, 保证录制始终是实时的

调用链路:

    POST /api/device/register   手动注册 (重复注册会被忽略)
    POST /api/device/bind       绑定到指定老人 (绑定后跌倒才会生成告警)
    POST /api/device/heartbeat  录制期间每 10 秒上报一次
    POST /api/device/video      跌倒证据视频(或 full 模式每段)上传到这里
    POST /api/device/stream     确认跌倒时, 上传那一帧截图

先启动后端 (python main.py, 端口 5000), 再运行:

    .venv\\Scripts\\python.exe tools\\camera_client.py --name 我的电脑摄像头 --elder-id 1

设备编号由服务器自动生成, 不需要填; 家属可以在家属端给它起名字(客厅/卧室)。
同一台电脑接两个摄像头时, 用 --camera 0 / --camera 1 区分, 会登记成两台设备。

没有摄像头时, 可以拿一个本地视频文件当信号源自测(视频里有跌倒画面才会产生告警):

    .venv\\Scripts\\python.exe tools\\camera_client.py --camera sample.mp4 --fps 10 --seconds 30

只想跑 AI 判定、不想上传录像(省流量):

    .venv\\Scripts\\python.exe tools\\camera_client.py --elder-id 1 --no-video

要像以前那样"每段都传服务器"(调试用):

    .venv\\Scripts\\python.exe tools\\camera_client.py --video-mode full

自定义证据视频长度 (默认 8+7=15 秒):

    .venv\\Scripts\\python.exe tools\\camera_client.py --elder-id 1 --pre-seconds 10 --post-seconds 10

验证:
    1. local 模式: recordings/{设备编号}/ 里每 10 秒多一个 segment_00N.mp4, static/videos 里没有新文件
    2. 跌倒时: 终端打印 [跌倒] -> [截图] 成功 -> [证据] 开始录制(前8秒已缓存) -> [证据] 完成上传
    3. 浏览器打开 http://127.0.0.1:5000/static/videos/CAM-PC-001/xxx.mp4 能播放, 摔倒点在视频中间
    4. MySQL 查:
       SELECT device_sn, status, last_online_time FROM device WHERE device_sn='CAM-PC-001';
       SELECT id, elder_id, alert_type, screenshot_path, create_time FROM alert ORDER BY id DESC LIMIT 5;

依赖: opencv-python / ultralytics(含 torch) / httpx, 都在 requirements.txt 里。
CPU 上模型预热后约 100ms/帧, 默认每 2 帧推理一次(--infer-every 2, 实测 CPU 可达 10fps)。
"""
import argparse
import collections
import queue
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("缺少 opencv-python, 请先执行: .venv\\Scripts\\pip.exe install -r requirements.txt")

try:
    import httpx
except ImportError:
    sys.exit("缺少 httpx, 请先执行: .venv\\Scripts\\pip.exe install -r requirements.txt")


# 允许直接以脚本方式运行(run 时 sys.path[0] 是 tools/, 这里补上项目根目录)
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

HEARTBEAT_INTERVAL = 10  # 心跳间隔(秒), 与后端建议值一致

# local 模式的本机录像目录(和 static/ 无关, 也不会上传):
# 像行车记录仪一样循环覆盖, 只保留最近 --keep-hours 小时
RECORDINGS_DIR = ROOT_DIR / "recordings"


# ---------------------------------------------------------------- 录制 / 上传


def open_writer(base_path: Path, fps: float, size: tuple[int, int]):
    """创建视频写入器: 优先 mp4(mp4v), 失败则退回 avi(MJPG)。

    返回 (writer, 实际文件路径, 扩展名); 全部失败返回 (None, None, None)。
    """
    writer = cv2.VideoWriter(str(base_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if writer.isOpened():
        return writer, base_path, ".mp4"
    writer.release()

    avi_path = base_path.with_suffix(".avi")
    writer = cv2.VideoWriter(str(avi_path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    if writer.isOpened():
        return writer, avi_path, ".avi"
    writer.release()
    return None, None, None


def upload_segment(client: httpx.Client, device_sn: str, path: Path, suffix: str) -> bool:
    """上传一段视频, 返回是否成功。"""
    content_type = "video/mp4" if suffix == ".mp4" else "video/x-msvideo"
    with open(path, "rb") as f:
        r = client.post(
            "/api/device/video",
            data={"device_sn": device_sn},
            files={"file": (path.name, f, content_type)},
        )
    if r.status_code == 200:
        data = r.json().get("data", {})
        print(f"[上传] 成功 {data.get('file_url')} ({data.get('size')} B)")
        return True
    print(f"[上传] 失败 {r.status_code}: {r.text}")
    return False


def prune_local(dir_path: Path, keep_hours: float) -> int:
    """删掉本机录像里超过保留时间的文件, 返回删除个数。

    这就是"循环覆盖": 目录里永远只有最近 keep_hours 小时的录像,
    不会越存越多把家里电脑的硬盘塞满。
    """
    if keep_hours <= 0 or not dir_path.is_dir():
        return 0
    cutoff = time.time() - keep_hours * 3600
    removed = 0
    for path in dir_path.glob("segment_*"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            pass
    return removed


# ---------------------------------------------------------------- AI 跌倒判定


def build_monitor(model_path: str | None, device: str = "cpu",
                  cooldown: float | None = None, per_track_cooldown: float | None = None):
    """加载跌倒检测器; 模型缺失/依赖缺失时抛异常, 由调用方决定是否降级。

    cooldown / per_track_cooldown 不传就用 fallwatch 的实时默认值(30s / 20s);
    演示"短时间内连摔多次"时调小, 否则第二次以后的跌倒会被冷却吞掉。
    """
    from infrastructure.ai.inference import FallMonitor

    return FallMonitor(
        model_path=model_path,
        device=device,
        cooldown_sec=cooldown,
        per_track_cooldown_sec=per_track_cooldown,
    )


def encode_snapshot(frame, detections, detector, quality: int = 85) -> bytes | None:
    """把当前帧(画上检测框)编码成 jpg 字节, 作为告警截图。"""
    img = frame.copy()
    if detections and detector is not None:
        try:
            detector.draw(img, detections)
        except Exception:
            pass  # 画框失败不影响截图本身
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return None
    return buf.tobytes()


def upload_snapshot(client: httpx.Client, device_sn: str, jpg_bytes: bytes, fall_conf: float) -> bool:
    """上传跌倒截图, 后端会存到 static/stream/{sn}/ 并生成告警。"""
    name = f"{device_sn}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
    r = client.post(
        "/api/device/stream",
        data={"device_sn": device_sn, "fall_conf": f"{fall_conf:.3f}"},
        files={"file": (name, jpg_bytes, "image/jpeg")},
    )
    if r.status_code == 200:
        body = r.json()
        data = body.get("data", {})
        print(
            f"[截图] 成功 {data.get('file_url')} ({data.get('size')} B) "
            f"alert_id={data.get('alert_id')} msg={body.get('msg')}"
        )
        return True
    print(f"[截图] 失败 {r.status_code}: {r.text}")
    return False


def run_detector(
    base_url: str,
    device_sn: str,
    monitor,
    frame_queue: "queue.Queue",
    stats: dict,
    event_queue: "queue.Queue | None" = None,
) -> None:
    """判定线程: 消费抽样帧 → 跑模型 → 跌倒就截图上传。

    退出条件: 主线程往队列里放 None。
    event_queue: 可选。判定到跌倒时往这里丢一个事件, 主线程收到后
    才把"跌倒前 N 秒 + 后 M 秒"的录像拼出来上传(ring 模式)。
    """
    warmed = False
    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        while True:
            item = frame_queue.get()
            if item is None:
                return
            frame, t = item

            try:
                # 第一次推理要初始化内核, 可能十几秒; 先用空白图预热, 避免漏判
                if not warmed:
                    print("[AI] 预热中(第一次推理较慢, 约 10 秒)...")
                    monitor.process(np.zeros((480, 640, 3), np.uint8), 0.0, run_inference=True)
                    warmed = True
                    print("[AI] 预热完成, 开始实时判定")

                result = monitor.process(frame, t, run_inference=True)
            except Exception as exc:
                print(f"[AI] 推理出错, 停止判定: {exc}")
                return

            for event in result.events:
                stats["events"] += 1
                print(
                    f"[跌倒] {event.event_id} track={event.track_id} "
                    f"conf={event.conf:.2f} 持续={event.duration_ms}ms box={event.box}"
                )
                # 先通知主线程开始留录像(ring 模式), 再截图上传, 少耽误几百毫秒
                if event_queue is not None:
                    try:
                        event_queue.put_nowait(event)
                    except queue.Full:
                        pass
                jpg = encode_snapshot(frame, result.detections, monitor.detector)
                if jpg is None:
                    print("[截图] 编码失败, 跳过本次上传")
                elif upload_snapshot(client, device_sn, jpg, event.conf):
                    stats["uploaded"] += 1


# ---------------------------------------------------------------- 主流程


def main() -> int:
    parser = argparse.ArgumentParser(
        description="用本机摄像头模拟设备: 连续录制 + 分段上传 + 本地跌倒判定 + 跌倒截图上报"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="后端地址")

    parser.add_argument("--name", default="", help="设备名称, 不填自动生成")
    parser.add_argument("--elder-id", type=int, default=None, help="要绑定的老人 id, 不填则跳过绑定")
    parser.add_argument("--camera", default="0", help="摄像头编号(默认 0), 也可传本地视频文件路径")
    parser.add_argument("--fps", type=float, default=20.0, help="录制帧率, 默认 20")
    parser.add_argument("--segment-seconds", type=float, default=10.0, help="每段视频时长(秒), 默认 10 (本机循环覆盖用)")
    parser.add_argument("--pre-seconds", type=float, default=8.0,
                        help="跌倒证据视频的'摔倒前'秒数, 默认 8; 摄像机预缓冲一直存这么多帧")
    parser.add_argument("--post-seconds", type=float, default=7.0,
                        help="跌倒证据视频的'摔倒后'秒数, 默认 7; AI 判定后再继续录这么久")
    parser.add_argument("--seconds", type=float, default=60.0, help="总录制时长(秒), <=0 表示一直录")

    parser.add_argument("--detect", dest="detect", action="store_true", default=None, help="强制开启跌倒判定")
    parser.add_argument("--no-detect", dest="detect", action="store_false", help="关闭跌倒判定, 只录像上传")
    parser.add_argument("--infer-every", type=int, default=2,
                        help="每 N 帧推理一次, 默认 2(实测 CPU 单帧 100ms, 每秒可判约 10 次)")
    parser.add_argument("--cooldown", type=float, default=None,
                        help="全局冷却秒数, 默认用实时配置 30; 演示连摔可调成 3~5")
    parser.add_argument("--per-track-cooldown", type=float, default=None,
                        help="同一个人两次告警最小间隔秒数, 默认用实时配置 20; 演示可调成 3~5")
    parser.add_argument("--model", default=None, help="模型路径, 默认用 config.settings.AI_MODEL_PATH")
    parser.add_argument("--device", default="cpu", help="推理设备 cpu / cuda:0, 默认 cpu")
    parser.add_argument("--no-video", dest="upload_video", action="store_false", default=True,
                        help="不上传录像片段, 只上传跌倒截图")
    parser.add_argument("--video-mode", choices=["local", "full"], default="local",
                        help="local=只存本机, 按 keep-hours 循环覆盖, 跌倒那一段才上传(默认); "
                             "full=每一段都上传(调试/演示用, 一天约 8GB)")
    parser.add_argument("--keep-hours", type=float, default=1.0,
                        help="local 模式本机录像保留小时数, 默认 1 小时")
    args = parser.parse_args()

    if args.segment_seconds <= 0:
        sys.exit("--segment-seconds 必须大于 0")
    if args.pre_seconds <= 0:
        sys.exit("--pre-seconds 必须大于 0")
    if args.post_seconds <= 0:
        sys.exit("--post-seconds 必须大于 0")
    if args.fps <= 0:
        sys.exit("--fps 必须大于 0")
    if args.infer_every < 1:
        sys.exit("--infer-every 必须 >= 1")
    if args.keep_hours <= 0:
        sys.exit("--keep-hours 必须大于 0")

    # --camera 既可以是编号 0/1, 也可以是视频文件路径
    source = int(args.camera) if str(args.camera).isdigit() else args.camera

    # 是否判定: 未显式指定时, 有模型文件就自动开启
    detect = args.detect
    if detect is None:
        from infrastructure.ai.model_loader import resolve_model_path

        detect = Path(resolve_model_path(args.model)).exists()
        print(f"[AI] 未指定 --detect/--no-detect, 按模型是否存在自动判定: {detect}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="elder_cam_"))
    cap = None
    writer = None
    monitor = None
    frame_queue: "queue.Queue" = queue.Queue(maxsize=1)
    event_queue: "queue.Queue" = queue.Queue(maxsize=10)
    stats = {"events": 0, "uploaded": 0}
    worker = None

    try:
        with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
            # ---- 1. 手动注册设备 ----
            # 硬件指纹: 同一台电脑重复运行会拿到同一个编号, 不会越注册越多
            import hashlib
            import uuid

            # 硬件指纹 = 本机 MAC + 摄像头来源
            # → 同一台电脑的 0 号 / 1 号摄像头会被识别成两台不同的设备
            machine = hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:24]
            source = hashlib.sha256(str(args.camera).encode()).hexdigest()[:8]
            hardware_id = f"pc-{machine}-{source}"

            payload = {
                "device_name": args.name or "我的电脑摄像头",
                "hardware_id": hardware_id,
            }
            r = client.post("/api/device/register", json=payload)
            if r.status_code != 200:
                print(f"[注册] 失败 {r.status_code}: {r.text}")
                return 1
            data = r.json().get("data") or {}
            args.sn = data.get("device_sn")
            if not args.sn:
                print("[注册] 没拿到设备编号, 退出")
                return 1
            print(f"[注册] 成功, 设备编号: {args.sn} (家属端给它起名字即可)")

            # ---- 2. 绑定老人 (可选) ----
            if args.elder_id is not None:
                r = client.post(
                    "/api/device/bind",
                    json={"device_sn": args.sn, "elder_id": args.elder_id},
                )
                if r.status_code == 200:
                    print(f"[绑定] 成功: {r.json().get('data')}")
                else:
                    print(f"[绑定] 失败 {r.status_code}: {r.text}")
                    return 1

            # ---- 3. 加载跌倒检测模型 + 启动判定线程 ----
            if detect:
                print("[AI] 正在加载跌倒检测模型, 第一次会比较慢...")
                try:
                    monitor = build_monitor(
                        args.model,
                        device=args.device,
                        cooldown=args.cooldown,
                        per_track_cooldown=args.per_track_cooldown,
                    )
                    names = sorted(monitor.detector.names.values())
                    print(f"[AI] 模型已加载, 类别 {names}, 每 {args.infer_every} 帧推理一次")
                except Exception as exc:
                    print(f"[AI] 模型加载失败, 本次只录像不判定: {exc}")
                    monitor = None

            if monitor is not None:
                worker = threading.Thread(
                    target=run_detector,
                    args=(args.base_url, args.sn, monitor, frame_queue, stats, event_queue),
                    daemon=True,
                    name="fall-detector",
                )
                worker.start()

            # ---- 4. 打开信号源 ----
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                print(f"[摄像头] 打不开 {args.camera}, 检查是否被其他程序占用")
                return 1

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width <= 0 or height <= 0:
                print("[摄像头] 读不到画面尺寸, 退出")
                return 1

            frames_per_segment = max(1, int(round(args.fps * args.segment_seconds)))
            print(
                f"[摄像头] 已打开 {args.camera} ({width}x{height}), "
                f"录制 {args.fps}fps, 每 {args.segment_seconds}s 切一段 "
                f"({frames_per_segment} 帧/段), 上传录像={args.upload_video}"
            )

            # ---- 录像策略 ----
            # 分段逻辑: local 模式录在本机 recordings/{sn}/, 只留最近 keep-hours 小时(循环覆盖),
            #           每 segment-seconds 秒切一段。full 模式每段都上传(调试用)。
            # 证据逻辑: 预缓冲一直存着最近 pre-seconds 秒的帧。AI 检测到跌倒时,
            #           立刻把这 pre 秒写进独立的证据视频, 再继续录 post 秒,
            #           然后上传 —— 不管摔倒在分段的第几秒, 证据视频里一定包含完整过程。
            local_mode = args.video_mode == "local" and args.upload_video
            work_dir = (RECORDINGS_DIR / args.sn) if local_mode else tmp_dir
            if local_mode:
                work_dir.mkdir(parents=True, exist_ok=True)
                removed = prune_local(work_dir, args.keep_hours)
                print(
                    f"[录制] local 模式: 录像存 {work_dir}, 只保留最近 {args.keep_hours} 小时 "
                    f"(启动时清了 {removed} 个旧文件)"
                )
            if args.upload_video:
                print(
                    f"[证据] 预缓冲 {args.pre_seconds:.0f}s + 后延 {args.post_seconds:.0f}s "
                    f"= 跌倒时自动拼 {args.pre_seconds + args.post_seconds:.0f}s 证据视频"
                )

            start = time.time()
            last_heartbeat = 0.0
            next_frame_at = time.time()
            frame_index = 0

            frames_per_segment = max(1, int(round(args.fps * args.segment_seconds)))
            # 预缓冲: 最多存 pre_seconds * fps 帧, 循环覆盖(超出自动丢最旧的)
            pre_buffer: collections.deque = collections.deque(
                maxlen=max(1, int(round(args.fps * args.pre_seconds)))
            )

            segment_no = 0
            seg_frames = 0
            seg_path = None
            seg_suffix = None
            uploaded = 0
            failed = 0

            # ---- 跌倒证据视频录制状态 ----
            fall_writer = None          # 当前正在写的证据视频 writer
            fall_path = None            # 证据视频文件路径
            fall_suffix = None          # 证据视频扩展名
            fall_started_at = 0.0       # 证据视频开始写入的时间戳(用来算 post-seconds)
            fall_frames = 0             # 证据视频已写帧数

            def _start_fall_evidence() -> None:
                """跌倒触发时调用: 把预缓冲里的帧立刻写进独立文件, 然后继续录 post 秒。"""
                nonlocal fall_writer, fall_path, fall_suffix, fall_started_at, fall_frames
                if not args.upload_video:
                    print("[证据] 不上传录像, 跳过证据视频录制 (--no-video)")
                    return
                if fall_writer is not None:
                    # 正在录上一段证据, 冷却期内不重叠 (避免两个事件同时录)
                    print("[证据] 上一段还没录完, 忽略本次跌倒事件")
                    return
                # 证据视频存到本机 work_dir (local 模式是 recordings/, full 模式是 tmp)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                base = work_dir / f"fall_{ts}.mp4"
                fall_writer, fall_path, fall_suffix = open_writer(base, args.fps, (width, height))
                if fall_writer is None:
                    print("[证据] 证据视频写入器创建失败, 跳过本次跌倒录制")
                    return
                # 先把预缓冲里的帧写进去 (这就是"摔倒前"的画面)
                pre_count = 0
                for cached_frame in pre_buffer:
                    fall_writer.write(cached_frame)
                    pre_count += 1
                fall_started_at = time.time()
                fall_frames = pre_count
                print(
                    f"[证据] 开始录制: 预缓冲 {pre_count} 帧 ({args.pre_seconds:.1f}s), "
                    f"接下来再录 {args.post_seconds:.1f}s 后上传"
                )

            def _finish_fall_evidence() -> None:
                """证据视频录满 post-seconds 后调用: 关闭文件并上传。"""
                nonlocal fall_writer, fall_path, fall_suffix, fall_frames
                if fall_writer is None:
                    return
                fall_writer.release()
                fall_writer = None
                print(f"[证据] 录制完成, 共 {fall_frames} 帧 -> {fall_path.name}")
                if args.video_mode == "full":
                    # full 模式证据视频也传
                    if upload_segment(client, args.sn, fall_path, fall_suffix):
                        uploaded += 1
                    else:
                        failed += 1
                    fall_path.unlink(missing_ok=True)
                else:
                    # local 模式: 跌倒触发的证据视频必须上传, 这是后端唯一能收到的
                    if upload_segment(client, args.sn, fall_path, fall_suffix):
                        uploaded += 1
                    else:
                        failed += 1
                        print(f"[证据] 上传失败, 本机副本保留: {fall_path.name}")
                    # local 模式下, 本机副本后续会被 prune_local 自动清理
                fall_path = None
                fall_suffix = None
                fall_frames = 0

            while args.seconds <= 0 or time.time() - start < args.seconds:
                ok, frame = cap.read()
                if not ok:
                    print("[摄像头] 读取画面失败, 提前结束")
                    break

                frame_index += 1

                # ---- 1) 预缓冲: 每帧都塞进去, 循环覆盖 (存最近 pre-seconds 秒) ----
                pre_buffer.append(frame.copy())

                # ---- 2) 抽样帧丢给判定线程 (队列满就丢旧帧, 绝不阻塞录制) ----
                if monitor is not None and frame_index % args.infer_every == 0:
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    frame_queue.put((frame.copy(), time.monotonic() - start))

                # ---- 3) 处理跌倒事件: 收到就立刻开始证据视频(不等分段录完) ----
                if event_queue is not None and not fall_writer:
                    try:
                        event_queue.get_nowait()
                        _start_fall_evidence()
                    except queue.Empty:
                        pass

                # ---- 4) 写当前帧到证据视频 (如果正在录) ----
                if fall_writer is not None:
                    fall_writer.write(frame)
                    fall_frames += 1
                    # post-seconds 到了就收尾上传
                    if time.time() - fall_started_at >= args.post_seconds:
                        _finish_fall_evidence()

                # ---- 5) 分段录像 (local 循环覆盖 / full 每段上传) ----
                if args.upload_video:
                    # 开新的一段 (segment_001.mp4 这种)
                    if writer is None:
                        segment_no += 1
                        base = work_dir / f"segment_{segment_no:03d}.mp4"
                        writer, seg_path, seg_suffix = open_writer(base, args.fps, (width, height))
                        if writer is None:
                            print("[录制] 分段写入器创建失败, 退出")
                            break
                        seg_frames = 0
                        print(f"[录制] 开始第 {segment_no} 段 -> {seg_path.name}")

                    if writer is not None:
                        writer.write(frame)
                        seg_frames += 1

                    # 录满一段 -> 关闭; full 模式全传, local 模式只存本机
                    if writer is not None and seg_frames >= frames_per_segment:
                        writer.release()
                        writer = None
                        if args.video_mode == "full":
                            if upload_segment(client, args.sn, seg_path, seg_suffix):
                                uploaded += 1
                            else:
                                failed += 1
                            seg_path.unlink(missing_ok=True)
                        else:
                            print(f"[录制] 第 {segment_no} 段存本机 (local, 不上传): {seg_path.name}")
                        if local_mode:
                            prune_local(work_dir, args.keep_hours)

                # ---- 6) 心跳: 每 10 秒一次 ----
                now = time.time()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    hb = client.post("/api/device/heartbeat", json={"device_sn": args.sn})
                    if hb.status_code == 200:
                        data = hb.json().get("data", {})
                        print(
                            f"[心跳] {hb.status_code} status={data.get('status')} "
                            f"last_online_time={data.get('last_online_time')}"
                        )
                    else:
                        print(f"[心跳] 失败 {hb.status_code}: {hb.text}")
                    last_heartbeat = now

                # 按帧率控制录制节奏
                next_frame_at += 1.0 / args.fps
                sleep_time = next_frame_at - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # ---- 5. 收尾 ----
            # 先处理还在录的证据视频 (没满 post-seconds 也要关掉上传)
            if fall_writer is not None:
                print(f"[证据] 收尾: 还有 {fall_frames} 帧未上传, 强制关闭并上传")
                _finish_fall_evidence()

            # 再处理最后一段没录满的分段
            if writer is not None:
                writer.release()
                writer = None
                if seg_frames > 0:
                    print(f"[录制] 收尾第 {segment_no} 段 ({seg_frames} 帧)")
                    if args.video_mode == "full":
                        if upload_segment(client, args.sn, seg_path, seg_suffix):
                            uploaded += 1
                        else:
                            failed += 1
                        seg_path.unlink(missing_ok=True)
                    else:
                        print(f"[录制] 已存本机 (local, 不上传): {seg_path.name}")

            if worker is not None:
                frame_queue.put(None)
                worker.join(timeout=120)

            print(
                f"\n[汇总] 视频上传成功 {uploaded} 段, 失败 {failed} 段; "
                f"跌倒事件 {stats['events']} 次, 截图上传成功 {stats['uploaded']} 次"
            )
            return 0
    except KeyboardInterrupt:
        print("\n[退出] 手动中断")
        return 0
    finally:
        # 清理没正常收尾的 writer (手动中断时会走到这里)
        if fall_writer is not None:
            try:
                fall_writer.release()
            except Exception:
                pass
        if writer is not None:
            writer.release()
        if cap is not None:
            cap.release()
        if worker is not None and worker.is_alive():
            try:
                frame_queue.put_nowait(None)
            except queue.Full:
                pass
            worker.join(timeout=30)
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
