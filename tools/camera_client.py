"""本机摄像头联调客户端 (Person A 硬件方向)。

模拟真实摄像头在**设备端**完成的两件事:

1. 连续录制实时画面, 按时间切成一段段视频 → 上传后端 (录像证据, /api/device/video)
2. 边录边跑跌倒检测 (复用 infrastructure/ai/inference.py 的 FallMonitor)
   → 只有确认跌倒的那一刻, 才把当前帧截图上传 (/api/device/stream)
   → 后端存图并生成 alert 告警记录, 家属/社康端就能看到

线程分工 (重要):
    录制线程(主线程)  读帧 → 写视频段 → 心跳 → 上传录像, 严格按 --fps 走, 不被 AI 拖慢
    判定线程          从队列里取"抽样的帧" → 跑模型 → 有跌倒事件就截图上传
    队列只留 1 帧     AI 跟不上时就丢掉旧帧, 保证录制始终是实时的

调用链路:

    POST /api/device/register   手动注册 (重复注册会被忽略)
    POST /api/device/bind       绑定到指定老人 (绑定后跌倒才会生成告警)
    POST /api/device/heartbeat  录制期间每 10 秒上报一次
    POST /api/device/video      每录满 --segment-seconds 秒, 上传一个视频片段
    POST /api/device/stream     确认跌倒时, 上传那一帧截图

先启动后端 (python main.py, 端口 5000), 再运行:

    .venv\\Scripts\\python.exe tools\\camera_client.py --sn CAM-PC-001 --name 我的电脑摄像头 --elder-id 1 --segment-seconds 10 --seconds 60

没有摄像头时, 可以拿一个本地视频文件当信号源自测(视频里有跌倒画面才会产生告警):

    .venv\\Scripts\\python.exe tools\\camera_client.py --sn CAM-TEST-001 --camera sample.mp4 --fps 10 --segment-seconds 2 --seconds 8

只想跑 AI 判定、不想上传录像(省流量):

    .venv\\Scripts\\python.exe tools\\camera_client.py --sn CAM-PC-001 --elder-id 1 --no-video

不跑 AI、只验证录制/上传链路:

    .venv\\Scripts\\python.exe tools\\camera_client.py --sn CAM-PC-001 --no-detect

验证:
    1. 终端打印 [录制] 第 N 段 -> [上传] 成功 /static/videos/CAM-PC-001/xxx.mp4
    2. 终端打印 [跌倒] E00xxx conf=0.8x -> [截图] 成功 /static/stream/CAM-PC-001/xxx.jpg alert_id=...
    3. 浏览器打开 http://127.0.0.1:5000/static/videos/CAM-PC-001/xxx.mp4 能播放
    4. MySQL 查:
       SELECT device_sn, status, last_online_time FROM device WHERE device_sn='CAM-PC-001';
       SELECT id, elder_id, alert_type, screenshot_path, create_time FROM alert ORDER BY id DESC LIMIT 5;

依赖: opencv-python / ultralytics(含 torch) / httpx, 都在 requirements.txt 里。
CPU 上模型预热后约 100ms/帧, 所以默认每 5 帧推理一次(--infer-every 5)。
"""
import argparse
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
) -> None:
    """判定线程: 消费抽样帧 → 跑模型 → 跌倒就截图上传。

    退出条件: 主线程往队列里放 None。
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
    parser.add_argument("--sn", required=True, help="设备序列号, 如 CAM-PC-001")
    parser.add_argument("--name", default="", help="设备名称, 不填自动生成")
    parser.add_argument("--elder-id", type=int, default=None, help="要绑定的老人 id, 不填则跳过绑定")
    parser.add_argument("--camera", default="0", help="摄像头编号(默认 0), 也可传本地视频文件路径")
    parser.add_argument("--fps", type=float, default=20.0, help="录制帧率, 默认 20")
    parser.add_argument("--segment-seconds", type=float, default=10.0, help="每段视频时长(秒), 默认 10")
    parser.add_argument("--seconds", type=float, default=60.0, help="总录制时长(秒), <=0 表示一直录")

    parser.add_argument("--detect", dest="detect", action="store_true", default=None, help="强制开启跌倒判定")
    parser.add_argument("--no-detect", dest="detect", action="store_false", help="关闭跌倒判定, 只录像上传")
    parser.add_argument("--infer-every", type=int, default=5, help="每 N 帧推理一次, 默认 5")
    parser.add_argument("--cooldown", type=float, default=None,
                        help="全局冷却秒数, 默认用实时配置 30; 演示连摔可调成 3~5")
    parser.add_argument("--per-track-cooldown", type=float, default=None,
                        help="同一个人两次告警最小间隔秒数, 默认用实时配置 20; 演示可调成 3~5")
    parser.add_argument("--model", default=None, help="模型路径, 默认用 config.settings.AI_MODEL_PATH")
    parser.add_argument("--device", default="cpu", help="推理设备 cpu / cuda:0, 默认 cpu")
    parser.add_argument("--no-video", dest="upload_video", action="store_false", default=True,
                        help="不上传录像片段, 只上传跌倒截图")
    args = parser.parse_args()

    if args.segment_seconds <= 0:
        sys.exit("--segment-seconds 必须大于 0")
    if args.fps <= 0:
        sys.exit("--fps 必须大于 0")
    if args.infer_every < 1:
        sys.exit("--infer-every 必须 >= 1")

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
    stats = {"events": 0, "uploaded": 0}
    worker = None

    try:
        with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
            # ---- 1. 手动注册设备 ----
            payload = {
                "device_sn": args.sn,
                "device_name": args.name or f"摄像头-{args.sn}",
            }
            r = client.post("/api/device/register", json=payload)
            if r.status_code == 400:
                print(f"[注册] 已注册过, 跳过: {r.json().get('msg')}")
            elif r.status_code == 200:
                print(f"[注册] 成功: {r.json().get('data')}")
            else:
                print(f"[注册] 失败 {r.status_code}: {r.text}")
                return 1

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
                    args=(args.base_url, args.sn, monitor, frame_queue, stats),
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

            start = time.time()
            last_heartbeat = 0.0
            next_frame_at = time.time()
            frame_index = 0

            segment_no = 0
            seg_frames = 0
            seg_path = None
            seg_suffix = None
            uploaded = 0
            failed = 0

            while args.seconds <= 0 or time.time() - start < args.seconds:
                ok, frame = cap.read()
                if not ok:
                    print("[摄像头] 读取画面失败, 提前结束")
                    break

                frame_index += 1

                # ---- 抽样帧丢给判定线程 (队列满就丢旧帧, 绝不阻塞录制) ----
                if monitor is not None and frame_index % args.infer_every == 0:
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    frame_queue.put((frame.copy(), time.monotonic() - start))

                # 开新的一段
                if writer is None and args.upload_video:
                    segment_no += 1
                    base = tmp_dir / f"segment_{segment_no:03d}.mp4"
                    writer, seg_path, seg_suffix = open_writer(base, args.fps, (width, height))
                    if writer is None:
                        print("[录制] 视频写入器创建失败, 退出")
                        break
                    seg_frames = 0
                    print(f"[录制] 开始第 {segment_no} 段 -> {seg_path.name}")

                if writer is not None:
                    writer.write(frame)
                    seg_frames += 1

                now = time.time()

                # 心跳: 每 10 秒一次
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

                # 录满一段 -> 关闭文件 -> 上传
                if writer is not None and seg_frames >= frames_per_segment:
                    writer.release()
                    writer = None
                    if upload_segment(client, args.sn, seg_path, seg_suffix):
                        uploaded += 1
                    else:
                        failed += 1
                    seg_path.unlink(missing_ok=True)

                # 按帧率控制录制节奏
                next_frame_at += 1.0 / args.fps
                sleep_time = next_frame_at - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # ---- 5. 收尾: 上传最后一段没录满的视频; 等判定线程跑完 ----
            if writer is not None:
                writer.release()
                writer = None
                if seg_frames > 0:
                    print(f"[录制] 收尾第 {segment_no} 段 ({seg_frames} 帧)")
                    if upload_segment(client, args.sn, seg_path, seg_suffix):
                        uploaded += 1
                    else:
                        failed += 1
                    seg_path.unlink(missing_ok=True)

            if worker is not None:
                frame_queue.put(None)
                worker.join(timeout=120)

            print(
                f"\n[汇总] 录像上传成功 {uploaded} 段, 失败 {failed} 段; "
                f"跌倒事件 {stats['events']} 次, 截图上传成功 {stats['uploaded']} 次"
            )
            return 0
    except KeyboardInterrupt:
        print("\n[退出] 手动中断")
        return 0
    finally:
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
