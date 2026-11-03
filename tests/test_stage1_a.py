"""阶段 1 (Person A) 接口自测脚本 —— 可直接反复运行。

运行:
    .venv\\Scripts\\python.exe tests\\test_stage1_a.py        (在项目根目录执行)

特点:
    - 用 FastAPI TestClient 直连真实 MySQL(读 config/settings_local.py), 会写库;
    - 所有测试数据用固定前缀 + 唯一 SN, 跑完在 finally 里自动清理(账号/设备/告警/文件);
    - 任一用例失败会打印失败名称并以非 0 退出, 方便在 CI 里跑。

覆盖 (35 个用例):
    auth   register / login / me            A1~A16
    device register / heartbeat / bind /
           stream / video                   D1~D14
"""
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

# tests/ 的上两级就是项目根目录
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

USER_A = "test_fam_a"
USER_B = "test_fam_b"
SN_OK = "CAM-A-TEST-001"
SN_NOBIND = "CAM-A-TEST-002"
TMP_VIDEO = ROOT / "_tmp_stage1.mp4"
TMP_JPG = ROOT / "_tmp_stage1.jpg"

passed = []


def check(name, cond, extra=""):
    assert cond, f"FAIL {name} {extra}"
    passed.append(name)
    print(f"  ✔ {name} {extra}")


def make_media():
    """造一张 jpg 和一段 20 帧的小视频, 当上传素材。"""
    img = np.full((120, 160, 3), 60, np.uint8)
    cv2.rectangle(img, (20, 30), (90, 110), (220, 220, 220), -1)
    cv2.imwrite(str(TMP_JPG), img)
    w = cv2.VideoWriter(str(TMP_VIDEO), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
    for _ in range(20):
        w.write(img)
    w.release()


def db_session():
    from db import session as dbs

    if dbs.SessionLocal is None:  # 应用还没启动过(lifespan 没跑)时手动初始化
        import config.settings as cfg

        dbs.init_session(cfg.DATABASE_URL)
    return dbs.SessionLocal()


def cleanup():
    from models import Alert, Device, User

    with db_session() as s:
        users = s.query(User).filter(User.username.in_([USER_A, USER_B])).all()
        ids = [u.id for u in users]
        if ids:
            s.query(Alert).filter(Alert.handled_by.in_(ids)).delete(synchronize_session=False)
        s.query(User).filter(User.username.in_([USER_A, USER_B])).delete(synchronize_session=False)
        for sn in (SN_OK, SN_NOBIND):
            dev = s.query(Device).filter(Device.device_sn == sn).first()
            if dev:
                s.query(Alert).filter(Alert.device_id == dev.id).delete(synchronize_session=False)
                s.delete(dev)
        s.commit()
    for sub in (SN_OK, SN_NOBIND):
        for base in ("stream", "videos"):
            shutil.rmtree(ROOT / "static" / base / sub, ignore_errors=True)
    TMP_VIDEO.unlink(missing_ok=True)
    TMP_JPG.unlink(missing_ok=True)


def main():
    import main as m
    from fastapi.testclient import TestClient

    cleanup()
    make_media()

    with TestClient(m.app) as c:
        # ---------------------------------------------------------- auth
        print("\n=== A. auth: register / login / me ===")

        r = c.post("/api/auth/register", json={
            "username": USER_A, "password": "Aa123456", "role": "family",
            "elder_id": 1, "phone": "13800001111",
        })
        check("A1 注册成功 -> 200", r.status_code == 200, r.text[:120])
        body = r.json()["data"]
        check("A1 返回 user_id/role/elder_id", body["user_id"] > 0 and body["role"] == "family"
              and body["elder_id"] == 1, str(body))
        check("A1 响应里没有密码字段", "password" not in body, str(list(body)))

        r = c.post("/api/auth/register", json={
            "username": USER_A, "password": "Aa123456", "role": "family"})
        check("A2 重复用户名 -> 400", r.status_code == 400 and "已被注册" in r.json()["msg"], r.text[:120])

        r = c.post("/api/auth/register", json={"username": USER_B, "password": "123", "role": "family"})
        check("A3 密码太短 -> 422", r.status_code == 422, r.text[:120])
        r = c.post("/api/auth/register", json={"username": USER_B, "password": "Aa123456", "role": "admin"})
        check("A4 role 非法 -> 422", r.status_code == 422, r.text[:120])
        r = c.post("/api/auth/register", json={"password": "Aa123456", "role": "family"})
        check("A5 缺 username -> 422", r.status_code == 422, r.text[:120])

        r = c.post("/api/auth/register", json={
            "username": USER_B, "password": "Aa123456", "role": "family", "elder_id": 999})
        check("A6 elder_id 不存在 -> 404", r.status_code == 404 and "999" in r.json()["msg"], r.text[:120])

        r = c.post("/api/auth/login", json={"username": USER_A, "password": "Aa123456"})
        check("A7 登录成功 -> 200", r.status_code == 200, r.text[:120])
        login = r.json()["data"]
        check("A7 返回 token/user_id/role/elder_id",
              len(login["token"]) > 20 and login["user_id"] == body["user_id"]
              and login["role"] == "family" and login["elder_id"] == 1, str(login)[:160])

        from infrastructure.security.jwt_tool import decode_token
        payload = decode_token(login["token"])
        check("A8 token 里的 user_id/role 正确",
              payload["user_id"] == login["user_id"] and payload["role"] == "family", str(payload))

        r = c.post("/api/auth/login", json={"username": USER_A, "password": "wrong-pwd"})
        check("A9 密码错 -> 401", r.status_code == 401 and r.json()["msg"] == "用户名或密码错误", r.text[:120])
        r = c.post("/api/auth/login", json={"username": "no_such_user", "password": "x"})
        check("A10 用户不存在 -> 401(提示与密码错一致)", r.status_code == 401, r.text[:120])

        # 种子账号是 werkzeug scrypt 哈希, 验证 password.py 的兼容分支
        r = c.post("/api/auth/login", json={"username": "admin", "password": "123456"})
        check("A11 种子账号 admin/123456 -> 200 (兼容 scrypt)", r.status_code == 200, r.text[:120])

        r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {login['token']}"})
        check("A12 /me 带 token -> 200", r.status_code == 200, r.text[:120])
        me = r.json()["data"]
        check("A12 /me 字段正确", me["id"] == login["user_id"] and me["username"] == USER_A
              and me["phone"] == "13800001111", str(me))

        r = c.get("/api/auth/me")
        check("A13 /me 不带 token -> 401", r.status_code == 401, r.text[:120])
        r = c.get("/api/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
        check("A14 /me 伪造 token -> 401", r.status_code == 401, r.text[:120])

        from jose import jwt
        import config.settings as cfg
        expired = jwt.encode({"sub": str(login["user_id"]), "role": "family",
                             "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
                             cfg.SECRET_KEY, algorithm=cfg.ALGORITHM)
        r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
        check("A15 过期 token -> 401", r.status_code == 401, r.text[:120])

        from models import User
        with db_session() as s:
            u = s.query(User).filter(User.username == USER_A).one()
            check("A16 数据库存 bcrypt 哈希而非明文",
                  u.password.startswith("$2b$") and "Aa123456" not in u.password, u.password[:10])

        # ---------------------------------------------------------- device
        print("\n=== B. device: register / heartbeat / stream / bind / video ===")

        r = c.post("/api/device/register", json={"device_sn": SN_OK, "device_name": "阶段1测试机"})
        check("D1 注册设备 -> 200 offline", r.status_code == 200 and r.json()["data"]["status"] == "offline",
              r.text[:120])
        r = c.post("/api/device/register", json={"device_sn": SN_OK, "device_name": "重复注册"})
        check("D2 重复注册 -> 400", r.status_code == 400, r.text[:120])

        r = c.post("/api/device/heartbeat", json={"device_sn": "CAM-NOT-EXIST"})
        check("D3 未注册设备心跳 -> 404", r.status_code == 404, r.text[:120])
        r = c.post("/api/device/heartbeat", json={"device_sn": SN_OK})
        check("D4 心跳 -> 200 online + last_online_time", r.status_code == 200
              and r.json()["data"]["status"] == "online" and r.json()["data"]["last_online_time"], r.text[:150])

        r = c.post("/api/device/bind", json={"device_sn": "CAM-NOT-EXIST", "elder_id": 1})
        check("D5 绑定不存在设备 -> 404", r.status_code == 404, r.text[:120])
        r = c.post("/api/device/bind", json={"device_sn": SN_OK, "elder_id": 999})
        check("D6 绑定不存在老人 -> 404", r.status_code == 404, r.text[:120])
        r = c.post("/api/device/bind", json={"device_sn": SN_OK, "elder_id": 1})
        check("D7 绑定成功 -> elder_id=1", r.status_code == 200 and r.json()["data"]["elder_id"] == 1,
              r.text[:120])

        with TMP_JPG.open("rb") as f:
            r = c.post("/api/device/stream", data={"device_sn": SN_OK, "fall_conf": "0.87"},
                       files={"file": ("fall.jpg", f, "image/jpeg")})
        check("D8 上传截图(已绑定) -> 200 有 alert_id", r.status_code == 200
              and r.json()["data"]["alert_id"] and r.json()["data"]["elder_id"] == 1, r.text[:160])
        shot = r.json()["data"]
        check("D8 截图落盘且静态可访问", (ROOT / shot["file_path"]).exists()
              and c.get(shot["file_url"]).status_code == 200, shot["file_url"])

        with db_session() as s:
            from models import Alert
            a = s.get(Alert, shot["alert_id"])
            check("D9 alert 行字段正确", a.alert_type == "fall" and a.elder_id == 1 and a.is_handled == 0
                  and a.screenshot_path == shot["file_path"].replace("static/", "", 1),
                  f"{a.alert_type}/{a.elder_id}/{a.is_handled}/{a.screenshot_path}")

        r = c.post("/api/device/stream", data={"device_sn": SN_OK},
                   files={"file": ("empty.jpg", b"", "image/jpeg")})
        check("D10 空截图 -> 400", r.status_code == 400, r.text[:120])

        c.post("/api/device/register", json={"device_sn": SN_NOBIND, "device_name": "未绑定测试机"})
        with TMP_JPG.open("rb") as f:
            r = c.post("/api/device/stream", data={"device_sn": SN_NOBIND},
                       files={"file": ("fall.jpg", f, "image/jpeg")})
        check("D11 未绑定上传截图 -> 200 但 alert_id=null 且有提示", r.status_code == 200
              and r.json()["data"]["alert_id"] is None and "未绑定" in r.json()["msg"], r.text[:160])

        with TMP_VIDEO.open("rb") as f:
            r = c.post("/api/device/video", data={"device_sn": SN_OK},
                       files={"file": ("seg.mp4", f, "video/mp4")})
        check("D12 上传视频片段 -> 200 落盘", r.status_code == 200
              and (ROOT / r.json()["data"]["file_path"]).exists(), r.text[:120])
        r = c.post("/api/device/video", data={"device_sn": SN_OK},
                   files={"file": ("empty.mp4", b"", "video/mp4")})
        check("D13 空视频 -> 400", r.status_code == 400, r.text[:120])
        r = c.post("/api/device/video", data={"device_sn": "CAM-NOT-EXIST"},
                   files={"file": ("x.mp4", b"xx", "video/mp4")})
        check("D14 未注册设备上传视频 -> 404", r.status_code == 404, r.text[:120])

        # ---- 不用重传: 检测该设备最新上传的视频 ----
        import types

        import infrastructure.ai.inference as inf

        class _FakeDetector:
            def draw(self, img, dets):
                return img

        class _FakeMonitor:
            """假判定器: 视频时间到 0.5s 时伪造一次跌倒事件, 用来验证截图/告警落库。"""

            def __init__(self, **kw):
                self.detector = _FakeDetector()
                self.fired = False

            def process(self, frame, t, run_inference=True):
                evs = []
                if not self.fired and t >= 0.5:
                    self.fired = True
                    evs = [types.SimpleNamespace(event_id="fake-latest", conf=0.9, box=(10, 10, 100, 150))]
                return types.SimpleNamespace(detections=[], events=evs)

        r = c.post("/api/device/detect/latest", data={"device_sn": SN_NOBIND})
        check("D15 设备没传过视频 -> 400", r.status_code == 400 and "还没有上传过视频" in r.json()["msg"],
              r.text[:140])

        real_monitor = inf.FallMonitor
        inf.FallMonitor = _FakeMonitor
        try:
            r = c.post("/api/device/detect/latest",
                       data={"device_sn": SN_OK, "infer_every": 1, "max_frames": 0})
        finally:
            inf.FallMonitor = real_monitor
        check("D16 检测最新视频 -> 200 并截到 1 帧", r.status_code == 200, r.text[:140])
        latest = r.json()["data"]
        check("D16 用的是刚才上传的那段视频", latest["video_path"].startswith(f"static/videos/{SN_OK}/"),
              latest["video_path"])
        check("D16 截图落盘 + alert 生成", latest["fall_events"] == 1
              and (ROOT / latest["screenshots"][0]["file_path"]).exists()
              and latest["screenshots"][0]["alert_id"], str(latest["screenshots"])[:160])

        # ---- /video?auto_detect=true: 上传后进后台队列自动检测 ----
        shots_before = len(list((ROOT / "static" / "stream" / SN_OK).glob("*.jpg")))
        inf.FallMonitor = _FakeMonitor
        try:
            with TMP_VIDEO.open("rb") as f:
                r = c.post("/api/device/video",
                           data={"device_sn": SN_OK, "auto_detect": "true"},
                           files={"file": ("auto.mp4", f, "video/mp4")})
            check("D17 auto_detect=true -> 200 且标记已排队", r.status_code == 200
                  and r.json()["data"]["auto_detect"] is True, r.text[:140])

            # 后台是单线程队列, 给 worker 一点时间把这段跑完
            deadline = time.time() + 40
            while time.time() < deadline:
                if len(list((ROOT / "static" / "stream" / SN_OK).glob("*.jpg"))) >= shots_before + 1:
                    break
                time.sleep(0.3)
            shots_after = len(list((ROOT / "static" / "stream" / SN_OK).glob("*.jpg")))
            check("D17 后台队列自动生成了跌倒截图", shots_after == shots_before + 1,
                  f"{shots_before} -> {shots_after}")
        finally:
            inf.FallMonitor = real_monitor

    print(f"\n共 {len(passed)} 个用例全部通过 ✔")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        cleanup()
        print("[清理] 测试账号/设备/告警/媒体文件已删除")
    sys.exit(code)
