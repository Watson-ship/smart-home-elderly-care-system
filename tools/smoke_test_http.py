"""HTTP 冒烟测试: 对着**已经在运行**的服务逐条打接口, 每一步都打印实际请求和结果。

和 tests/test_stage1_a.py 的区别:
    - 那个用 FastAPI TestClient(进程内, 不用启动服务, 适合提交作业前回归);
    - 这个用真实 HTTP(必须先启动 main.py), 适合"我到底能不能调通"的自检,
      也是验收演示用的脚本。

用法 (先启动服务, 另开一个窗口跑):
    .venv\\Scripts\\python.exe tools\\smoke_test_http.py
    .venv\\Scripts\\python.exe tools\\smoke_test_http.py --base-url http://127.0.0.1:5001
    .venv\\Scripts\\python.exe tools\\smoke_test_http.py --video "D:\\我的摔倒视频.mp4"   # 额外跑 /detect

每一步的期望值都写在代码里, 失败会打印 [FAIL] 并以非 0 退出。
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import httpx

try:
    import cv2
    import numpy as np
except ImportError:  # 没装 opencv 时只测文本接口
    cv2 = None
    np = None


class Smoke:
    def __init__(self, base_url: str, elder_id: int):
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base, timeout=600.0)
        self.elder_id = elder_id
        stamp = time.strftime("%H%M%S")
        self.sn = f"CAM-SMOKE-{stamp}"
        self.user = f"smoke_{stamp}"
        self.ok = 0
        self.fail = 0

    # ------------------------------------------------------------ 打印工具
    def step(self, no: int, total: int, text: str):
        print(f"[{no:2d}/{total}] {text:<62}", end="", flush=True)

    def done(self, resp: httpx.Response, expect: int, note: str = "") -> dict | None:
        good = resp.status_code == expect
        body = None
        try:
            body = resp.json()
        except ValueError:
            pass
        if good and body is not None and body.get("code") != 0 and expect == 200:
            good = False  # code 不为 0 也算失败
        print(("✔ " if good else "✘ ") + f"{resp.status_code} {note}")
        if not good:
            self.fail += 1
            print("       实际响应:", resp.text[:300])
        else:
            self.ok += 1
        return body

    def finish(self):
        self.client.close()
        print("\n" + "=" * 70)
        if self.fail == 0:
            print(f"全部通过: {self.ok} 个请求 ✔")
        else:
            print(f"通过 {self.ok} 个, 失败 {self.fail} 个 ✘")
        print(f"本次测试创建了设备 {self.sn} 和账号 {self.user}(可留作演示, 也可删)")
        print("=" * 70)
        return 0 if self.fail == 0 else 1


def make_media(tmp: Path) -> tuple[Path, Path]:
    """造一张 jpg 和一段 1 秒的小视频当上传素材(没有 opencv 时用假字节)。"""
    jpg = tmp / "smoke.jpg"
    mp4 = tmp / "smoke.mp4"
    if cv2 is None:
        jpg.write_bytes(b"\xff\xd8\xff\xd9")  # 最小 jpg
        mp4.write_bytes(b"fake")
        return jpg, mp4
    img = np.full((180, 240, 3), 70, dtype=np.uint8)
    cv2.rectangle(img, (30, 40), (140, 160), (210, 210, 210), -1)
    cv2.imwrite(str(jpg), img)
    w = cv2.VideoWriter(str(mp4), cv2.VideoWriter_fourcc(*"mp4v"), 10, (240, 180))
    for _ in range(10):
        w.write(img)
    w.release()
    return jpg, mp4


def main() -> int:
    ap = argparse.ArgumentParser(description="HTTP 冒烟测试")
    ap.add_argument("--base-url", default="http://127.0.0.1:5000", help="服务地址")
    ap.add_argument("--elder-id", type=int, default=1, help="绑定到哪个老人(种子数据里 1~10)")
    ap.add_argument("--video", default=None, help="可选: 用它跑 /api/device/detect")
    ap.add_argument("--skip-detect", action="store_true", help="不自动跑 /detect(省时间)")
    args = ap.parse_args()

    s = Smoke(args.base_url, args.elder_id)
    # 固定 15 个请求, 带视频再跑 /detect 就是 16 个
    total = 16 if (args.video and not args.skip_detect) else 15
    n = 0
    tmp_dir = Path(tempfile.mkdtemp(prefix="smoke_"))
    jpg, mp4 = make_media(tmp_dir)

    def bump():
        nonlocal n
        n += 1
        return n, total

    # 1 连通性
    i, t = bump()
    s.step(i, t, "GET  /health  服务是否还活着")
    s.done(s.client.get("/health"), 200)

    i, t = bump()
    s.step(i, t, "GET  /  根路径导航")
    s.done(s.client.get("/"), 200)

    # 2 auth
    i, t = bump()
    s.step(i, t, f"POST /api/auth/register  注册 {s.user}")
    s.done(s.client.post("/api/auth/register", json={
        "username": s.user, "password": "Aa123456", "role": "family",
        "elder_id": args.elder_id, "phone": "13800009999"}), 200)

    i, t = bump()
    s.step(i, t, "POST /api/auth/register  重复注册应被拒绝")
    s.done(s.client.post("/api/auth/register", json={
        "username": s.user, "password": "Aa123456", "role": "family"}), 400)

    i, t = bump()
    s.step(i, t, "POST /api/auth/login  用错密码应 401")
    s.done(s.client.post("/api/auth/login", json={"username": s.user, "password": "wrong"}), 401)

    i, t = bump()
    s.step(i, t, "POST /api/auth/login  正确登录拿 token")
    body = s.done(s.client.post("/api/auth/login", json={
        "username": s.user, "password": "Aa123456"}), 200)
    token = (body or {}).get("data", {}).get("token", "")

    i, t = bump()
    s.step(i, t, "GET  /api/auth/me  带 token 取当前用户")
    s.done(s.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}), 200)

    i, t = bump()
    s.step(i, t, "GET  /api/auth/me  不带 token 应 401")
    s.done(s.client.get("/api/auth/me"), 401)

    i, t = bump()
    s.step(i, t, "POST /api/auth/login  种子账号 admin/123456")
    s.done(s.client.post("/api/auth/login", json={"username": "admin", "password": "123456"}), 200)

    # 3 device
    i, t = bump()
    s.step(i, t, f"POST /api/device/register  注册 {s.sn}")
    s.done(s.client.post("/api/device/register", json={
        "device_sn": s.sn, "device_name": "冒烟测试摄像头"}), 200)

    i, t = bump()
    s.step(i, t, "POST /api/device/heartbeat  未注册设备应 404")
    s.done(s.client.post("/api/device/heartbeat", json={"device_sn": "CAM-NOT-EXIST"}), 404)

    i, t = bump()
    s.step(i, t, "POST /api/device/heartbeat  心跳置 online")
    s.done(s.client.post("/api/device/heartbeat", json={"device_sn": s.sn}), 200)

    i, t = bump()
    s.step(i, t, f"POST /api/device/bind  绑定到老人 {args.elder_id}")
    s.done(s.client.post("/api/device/bind", json={
        "device_sn": s.sn, "elder_id": args.elder_id}), 200)

    i, t = bump()
    s.step(i, t, "POST /api/device/stream  上传跌倒截图(应生成 alert)")
    with jpg.open("rb") as f:
        body = s.done(s.client.post("/api/device/stream",
                                    data={"device_sn": s.sn, "fall_conf": "0.91"},
                                    files={"file": ("fall.jpg", f, "image/jpeg")}), 200)
    shot = (body or {}).get("data", {})
    if shot.get("file_url"):
        print(f"        截图地址: {s.base}{shot['file_url']}  (alert_id={shot.get('alert_id')})")
        print(f"        浏览器打开看看是不是你传的那张图")

    i, t = bump()
    s.step(i, t, "POST /api/device/video  上传录像片段")
    with mp4.open("rb") as f:
        s.done(s.client.post("/api/device/video", data={"device_sn": s.sn},
                             files={"file": ("seg.mp4", f, "video/mp4")}), 200)

    # 4 detect(可选: 有视频/没跳过时跑)
    video = Path(args.video) if args.video else None
    if not args.skip_detect:
        if video is None:
            print("\n提示: 想看跌倒检测, 把你的视频传上来时加参数 --video \"D:\\你的视频.mp4\"")
            print(f"      也可以直接对着 Swagger 手动传: {s.base}/docs")
        elif not video.exists():
            print(f"\n[提示] 找不到视频 {video}, 跳过 /detect")
        else:
            i, t = bump()
            s.step(i, t, f"POST /api/device/detect  {video.name} (模型首次加载较慢)")
            with video.open("rb") as f:
                body = s.done(s.client.post("/api/device/detect",
                                            data={"device_sn": s.sn, "infer_every": "3",
                                                  "max_frames": "0",
                                                  "require_transition": "false"},
                                            files={"file": (video.name, f, "video/mp4")}), 200)
            data = (body or {}).get("data", {})
            print(f"        处理帧数={data.get('frames_processed')} 事件数={data.get('fall_events')} "
                  f"耗时={data.get('elapsed_ms')}ms")
            for item in data.get("screenshots", []):
                print(f"        摔倒帧: {s.base}{item['file_url']}  "
                      f"毫秒={item['time_ms']} 置信度={item['conf']} alert={item['alert_id']}")

    return s.finish()


if __name__ == "__main__":
    sys.exit(main())
