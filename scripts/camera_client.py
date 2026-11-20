"""摄像头实时推流客户端 (阶段 3, Person A 硬件方向)。

把"手动 POST 图片"变成"真摄像头自己推流":

    每 2 秒    从摄像头读一帧 -> POST /api/device/frame   (只进内存, 不建告警)
    每 10 秒   POST /api/device/heartbeat                (刷新在线状态)
    断线       自动重连(摄像头被拔/RTSP 掉线/后端重启都不会让脚本退出)
    上传失败   指数退避重试, 重试完还是失败就打日志继续跑, 绝不影响下一帧

家属端只需要一个 <img>, 就能看到"动起来"的画面(服务端拼成 MJPEG 流):

    <img src="http://127.0.0.1:5000/api/device/live/CAM-PC-001">

用法(先 python main.py 启动后端):

    先看看这台电脑有几路摄像头:
        .venv\\Scripts\\python.exe scripts\\camera_client.py --sn CAM-PC-001 --list-cameras

    启动时手动选一路(推荐, 不用记编号):
        .venv\\Scripts\\python.exe scripts\\camera_client.py --sn CAM-PC-001 --pick

    本机摄像头 0:
        .venv\\Scripts\\python.exe scripts\\camera_client.py --sn CAM-PC-001 --camera 0

    第二台(同学 B):  --sn CAM-PC-002 --camera 1
    第三台(同学 C):  --sn CAM-PC-003 --camera 2      # 三人各跑一个 = 多设备

    用**别人电脑**上的摄像头(摄像头物理在对方机器上, 只能由那台机器推流):
        1) 你的后端要以局域网模式启动:  HOST=0.0.0.0 python main.py
           启动时会打印 "局域网: http://192.168.x.x:5000"
        2) 在对方电脑上跑本脚本, --base-url 指向你的地址:
           python scripts\\camera_client.py --sn CAM-B-PC --camera 0 --base-url http://192.168.x.x:5000

    RTSP 网络摄像头:
        .venv\\Scripts\\python.exe scripts\\camera_client.py --sn CAM-101 --camera "rtsp://admin:12345@192.168.1.64:554/stream1"

    没有摄像头时, 用一段视频文件当信号源(会循环播放):
        .venv\\Scripts\\python.exe scripts\\camera_client.py --sn CAM-TEST-001 --camera sample.mp4

    推 2 分钟就停(默认一直推, Ctrl+C 结束):
        .venv\\Scripts\\python.exe scripts\\camera_client.py --sn CAM-PC-001 --seconds 120

验证:
    1. 终端: [注册] / [心跳] / [推流] 成功 ... 每 2 秒一行
    2. 浏览器打开 /api/device/live/{sn} -> 画面会动
    3. 拔掉摄像头/停掉后端 5 秒再重启 -> 终端打印 [重连] 并自动恢复, 脚本不退出

和 tools/camera_client.py 的区别:
    tools/  (阶段 1)  连续录像分段上传 + 本地 AI 跌倒判定 + 只传摔倒那一帧
    scripts/(阶段 3)  实时推帧给家属端看"直播", 不做 AI, 不做录像
    两者可以同时跑(同一个 SN 建议只跑一个, 避免抢摄像头)
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import cv2
except ImportError:
    sys.exit("缺少 opencv-python, 请先执行: .venv\\Scripts\\pip.exe install -r requirements.txt")

try:
    import httpx
except ImportError:
    sys.exit("缺少 httpx, 请先执行: .venv\\Scripts\\pip.exe install -r requirements.txt")

IMAGE_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".jpg", ".png"}


def log(msg: str) -> None:
    """带时间的日志, 演示时一眼看出"多久没心跳/多久没推帧"。"""
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- HTTP 重试


def post_with_retry(
    client: httpx.Client,
    path: str,
    *,
    data: dict | None = None,
    files: dict | None = None,
    retries: int = 3,
) -> "httpx.Response | None":
    """POST 带指数退避重试: 1s -> 2s -> 4s。

    只重试"网络异常"和"5xx"(后端临时挂了);
    4xx 是我们自己的请求错了(设备没注册等), 重试没用, 直接返回给调用方判断。
    """
    delay = 1.0
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            r = client.post(path, data=data, files=files)
            if r.status_code < 500:
                return r
            last_error = f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < retries:
            log(f"[重试] {path} 第 {attempt}/{retries} 次失败({last_error}), {delay:.0f}s 后重试")
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    log(f"[重试] {path} 连续 {retries} 次失败, 放弃本次: {last_error}")
    return None


def post_json_with_retry(
    client: httpx.Client, path: str, payload: dict, retries: int = 3
) -> "httpx.Response | None":
    """JSON 请求的重试版(注册/心跳用), 逻辑同 post_with_retry。"""
    delay = 1.0
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            r = client.post(path, json=payload)
            if r.status_code < 500:
                return r
            last_error = f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < retries:
            log(f"[重试] {path} 第 {attempt}/{retries} 次失败({last_error}), {delay:.0f}s 后重试")
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    log(f"[重试] {path} 连续 {retries} 次失败, 放弃本次: {last_error}")
    return None


def register_and_bind(
    client: httpx.Client, sn: str, name: str, elder_id: int | None, retries: int
) -> bool:
    """注册设备(已注册就跳过) + 可选绑定老人。返回 False 表示后端不可达。"""
    resp = post_json_with_retry(
        client, "/api/device/register", {"device_sn": sn, "device_name": name}, retries
    )
    if resp is None:
        log("[注册] 后端不可达, 请先启动 python main.py")
        return False

    if resp.status_code == 200:
        log(f"[注册] 成功 {resp.json().get('data')}")
    elif resp.status_code == 400:
        log(f"[注册] 已注册过, 跳过: {resp.json().get('msg')}")
    else:
        log(f"[注册] 失败 {resp.status_code}: {resp.text}")
        return False

    if elder_id is not None:
        r = post_json_with_retry(
            client, "/api/device/bind", {"device_sn": sn, "elder_id": elder_id}, retries
        )
        if r is not None and r.status_code == 200:
            log(f"[绑定] 成功 elder_id={elder_id}")
        elif r is not None:
            log(f"[绑定] 失败 {r.status_code}: {r.text}")

    return True


# ---------------------------------------------------------------- 摄像头


def open_camera(source, retries: int = 5, delay: float = 3.0):
    """打开摄像头/RTSP/视频文件; 失败按次重试。"""
    for attempt in range(1, retries + 1):
        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            log(f"[摄像头] 已打开 {source} ({w}x{h})")
            return cap
        cap.release()
        if attempt < retries:
            log(f"[摄像头] 打开失败 第 {attempt}/{retries} 次, {delay:.0f}s 后重试")
            time.sleep(delay)
    return None


def encode_jpeg(frame, quality: int, max_width: int) -> bytes | None:
    """编码成 jpg; 超过 max_width 等比缩小, 省带宽也省后端内存。"""
    img = frame
    if max_width > 0 and frame.shape[1] > max_width:
        scale = max_width / frame.shape[1]
        img = cv2.resize(
            frame, (max_width, int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA
        )
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def list_cameras(max_index: int = 5) -> list[tuple[int, int, int]]:
    """探测本机有哪些可用摄像头, 返回 [(编号, 宽, 高)]。

    OpenCV 没有"枚举设备"的接口, 只能从 0 开始逐个尝试打开。
    Windows 上用 DSHOW 后端比默认 MSMF 快, 探测也更稳。
    """
    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
    found = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, backend)
        if cap.isOpened() and cap.read()[0]:
            found.append(
                (
                    idx,
                    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                )
            )
        cap.release()
    return found


def print_cameras(max_index: int) -> list[tuple[int, int, int]]:
    """打印可用摄像头清单, 直接告诉用户 --camera 该填几。"""
    cams = list_cameras(max_index)
    if not cams:
        print(f"没有检测到可用的本机摄像头(试过 0~{max_index - 1})。")
        print("可以用 RTSP 网络摄像头, 或用视频文件模拟:")
        print("  --camera \"rtsp://admin:密码@192.168.1.64:554/stream1\"")
        print("  --camera sample.mp4")
        return cams
    print(f"检测到 {len(cams)} 个可用摄像头:")
    for idx, w, h in cams:
        print(f"  编号 {idx}: {w}x{h}    ->  --camera {idx}")
    print("\n别人的电脑: 在那台电脑上跑同样的命令(用它的摄像头), --base-url 指到你的后端,")
    print("后端需以 HOST=0.0.0.0 启动, 例如 --base-url http://192.168.1.5:5000")
    return cams


# ---------------------------------------------------------------- 主流程


def main() -> int:
    parser = argparse.ArgumentParser(
        description="摄像头实时推流: 每 2 秒推一帧到 /api/device/frame, 每 10 秒心跳, 断线自动重连"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="后端地址")
    parser.add_argument("--sn", required=True, help="设备序列号, 如 CAM-PC-001(多设备就是不同 SN)")
    parser.add_argument("--name", default="", help="设备名称, 不填自动生成")
    parser.add_argument("--elder-id", type=int, default=None, help="绑定到哪个老人, 不填则跳过绑定")
    parser.add_argument("--camera", default="0", help="摄像头编号 0/1/2, 或 RTSP 地址, 或视频文件路径")
    parser.add_argument("--frame-interval", type=float, default=2.0, help="推帧间隔(秒), 默认 2")
    parser.add_argument("--heartbeat-interval", type=float, default=10.0, help="心跳间隔(秒), 默认 10")
    parser.add_argument("--fps", type=float, default=15.0, help="读摄像头帧率上限, 默认 15")
    parser.add_argument("--quality", type=int, default=80, help="jpg 质量 1~100, 默认 80")
    parser.add_argument("--max-width", type=int, default=640, help="推流最大宽度, 0 表示不缩放")
    parser.add_argument("--retries", type=int, default=3, help="单次上传失败重试次数, 默认 3")
    parser.add_argument("--reconnect-delay", type=float, default=3.0, help="摄像头断线后重连间隔(秒)")
    parser.add_argument("--seconds", type=float, default=0, help="推流总时长(秒), <=0 表示一直推")
    parser.add_argument("--no-loop-file", dest="loop_file", action="store_false", default=True,
                        help="视频文件播完不循环(默认循环, 方便无摄像头演示)")
    parser.add_argument("--list-cameras", nargs="?", const=5, type=int, default=None, metavar="N",
                        help="列出本机可用摄像头(探测 0~N-1)后退出, 不传 N 默认 5")
    parser.add_argument("--pick", action="store_true",
                        help="启动前先列出摄像头并让你选一个编号(接多摄像头时省事)")
    args = parser.parse_args()

    # ---- 选择要接哪一路摄像头 ----
    if args.list_cameras is not None:
        print_cameras(max(args.list_cameras, 1))
        return 0
    if args.pick:
        cams = print_cameras(5)
        if not cams:
            return 1
        try:
            choice = int(input("\n输入要使用的摄像头编号: ").strip())
        except (EOFError, ValueError):
            print("输入无效, 退出")
            return 1
        if choice not in [c[0] for c in cams]:
            print(f"编号 {choice} 不在可用列表里, 退出")
            return 1
        args.camera = str(choice)
        print(f"已选择摄像头 {choice}")

    if args.frame_interval <= 0:
        sys.exit("--frame-interval 必须大于 0")
    if args.heartbeat_interval <= 0:
        sys.exit("--heartbeat-interval 必须大于 0")
    if args.fps <= 0:
        sys.exit("--fps 必须大于 0")

    # --camera 既可以是编号(0/1), 也可以是 rtsp:// 或本地文件
    camera_arg = str(args.camera)
    source = int(camera_arg) if camera_arg.isdigit() else camera_arg
    is_file = (not camera_arg.isdigit()) and Path(camera_arg).suffix.lower() in IMAGE_SUFFIXES

    stats = {"frames_ok": 0, "frames_fail": 0, "beats_ok": 0, "beats_fail": 0, "reconnects": 0}
    start = time.time()

    with httpx.Client(base_url=args.base_url, timeout=15.0) as client:
        if not register_and_bind(
            client, args.sn, args.name or f"摄像头-{args.sn}", args.elder_id, args.retries
        ):
            return 1

        cap = open_camera(source)
        if cap is None:
            log("[摄像头] 打不开, 检查编号是否正确/是否被其他程序占用")
            return 1

        log(
            f"[推流] 设备={args.sn} 每 {args.frame_interval}s 推一帧, "
            f"每 {args.heartbeat_interval}s 心跳; 家属端看: "
            f"{args.base_url}/api/device/live/{args.sn}"
        )

        next_frame_at = time.time()
        last_heartbeat = 0.0
        try:
            while args.seconds <= 0 or time.time() - start < args.seconds:
                ok, frame = cap.read()

                if not ok:
                    # ---- 断线重连: 视频文件播完从头开始, 摄像头/RTSP 重新打开 ----
                    if is_file and not args.loop_file:
                        log("[重连] 视频文件已播完(--no-loop-file), 结束")
                        break
                    stats["reconnects"] += 1
                    log(f"[重连] 第 {stats['reconnects']} 次读帧失败, {args.reconnect_delay:.0f}s 后重连")
                    cap.release()
                    time.sleep(args.reconnect_delay)
                    cap = open_camera(source)
                    if cap is None:
                        log("[重连] 摄像头仍然打不开, 继续重试(按 Ctrl+C 退出)")
                    next_frame_at = time.time()
                    continue

                now = time.time()

                # ---- 每 2 秒推一帧 ----
                if now >= next_frame_at:
                    jpg = encode_jpeg(frame, args.quality, args.max_width)
                    if jpg is None:
                        stats["frames_fail"] += 1
                        log("[推流] 编码失败, 跳过这一帧")
                    else:
                        r = post_with_retry(
                            client,
                            "/api/device/frame",
                            data={"device_sn": args.sn},
                            files={"file": (f"{args.sn}.jpg", jpg, "image/jpeg")},
                            retries=args.retries,
                        )
                        if r is not None and r.status_code == 200:
                            stats["frames_ok"] += 1
                            body = r.json().get("data", {})
                            log(
                                f"[推流] 成功 {len(jpg)}B 观看人数={body.get('viewers')} "
                                f"(累计 {stats['frames_ok']} 帧)"
                            )
                        elif r is not None and r.status_code == 404:
                            stats["frames_fail"] += 1
                            log(f"[推流] 设备未注册被拒: {r.text[:120]}, 尝试重新注册")
                            register_and_bind(
                                client, args.sn, args.name or f"摄像头-{args.sn}",
                                args.elder_id, args.retries,
                            )
                        else:
                            stats["frames_fail"] += 1
                            if r is not None:
                                log(f"[推流] 失败 {r.status_code}: {r.text[:120]}")
                    next_frame_at = now + args.frame_interval

                # ---- 每 10 秒心跳 ----
                if now - last_heartbeat >= args.heartbeat_interval:
                    hb = post_json_with_retry(
                        client, "/api/device/heartbeat", {"device_sn": args.sn}, args.retries
                    )
                    if hb is not None and hb.status_code == 200:
                        stats["beats_ok"] += 1
                        data = hb.json().get("data", {})
                        log(f"[心跳] OK status={data.get('status')} last={data.get('last_online_time')}")
                    else:
                        stats["beats_fail"] += 1
                        if hb is not None:
                            log(f"[心跳] 失败 {hb.status_code}: {hb.text[:120]}")
                    last_heartbeat = now

                # ---- 控制读帧节奏(不推流时也别空转烧 CPU) ----
                time.sleep(max(0.0, 1.0 / args.fps))
        except KeyboardInterrupt:
            log("[退出] 手动中断")
        finally:
            cap.release()
            log(
                f"[汇总] 推帧成功 {stats['frames_ok']} / 失败 {stats['frames_fail']}, "
                f"心跳成功 {stats['beats_ok']} / 失败 {stats['beats_fail']}, "
                f"重连 {stats['reconnects']} 次"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
