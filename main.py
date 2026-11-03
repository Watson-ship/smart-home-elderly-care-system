"""应用入口: 创建 FastAPI 实例, 初始化数据库, 注册所有路由。
启动方式:
  python main.py               # 直接运行(带 reload 自动重启)
  uvicorn main:app --reload    # 同上, 命令行方式
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import config.settings as settings
from db.base import Base
from db.session import init_session
from schemas.common_schema import BaseResp, HealthResp, ok


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期: 启动时连库建表, 空表自动插种子, 关闭时清理。"""
    if "你的密码" in settings.DATABASE_URL:
        raise RuntimeError(
            "数据库未配置：请复制 config/settings_local.example.py 为 "
            "config/settings_local.py 并填入 MySQL 密码，"
            "或设置环境变量 DATABASE_URL 后重试。"
        )

    init_session(settings.DATABASE_URL)

    # 导入所有模型, 让 Base.metadata 能发现所有表
    from models import Elder, User, Device, MedicinePlan, MedicineRecord, Alert, WorkOrder  # noqa: F401,F841
    from db.session import engine, SessionLocal

    Base.metadata.create_all(engine)  # 首次运行自动建表(也可手动执行 sql/init.sql)
    print(f"[启动] 数据库连接成功: {settings.DATABASE_URL}")
    print(f"[启动] 已自动建表, 共 {len(Base.metadata.tables)} 张")

    # 空表自动插种子数据
    from db.seed import seed_if_empty
    with SessionLocal() as session:
        seed_if_empty(session)

    yield
    print("[关闭] 应用已清理")


app = FastAPI(
    title="居家老人监测系统 API",
    description="后端接口文档 —— 小组协作直接打开这个调接口",
    version="0.1.0",
    lifespan=lifespan,
)

# ---- 静态文件: 设备上传的视频、告警截图都从这里访问 ----
# 例: /static/videos/CAM-SN-001/20261027_140211_288.mp4
from pathlib import Path

Path("static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---- 统一异常响应: 让错误也长成 {code, msg, data} 的样子 ----
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTPException(404/400...) 统一转成 {code, msg, data}。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": str(exc.detail), "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 参数校验失败: code=422, data 里放具体哪个字段错了。"""
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"code": 422, "msg": "参数校验失败", "data": exc.errors()}),
    )


# ---- 健康检查 ----
@app.get("/health", response_model=BaseResp[HealthResp], summary="健康检查")
def health():
    """验证服务器和数据库都正常"""
    return ok(HealthResp(status="ok"))


# ---- 注册所有业务路由 ----
# 每个 domain 一个 router, 前缀和 tag 在各自 routes.py 里定义
from domains.auth.routes import router as auth_router
from domains.elder.routes import router as elder_router
from domains.device.routes import router as device_router
from domains.alert.routes import router as alert_router
from domains.medicine.routes import router as medicine_router
from domains.work_order.routes import router as work_order_router

app.include_router(auth_router)
app.include_router(elder_router)
app.include_router(device_router)
app.include_router(alert_router)
app.include_router(medicine_router)
app.include_router(work_order_router)


# ---- 根路径: 直接访问 http://localhost:5000/ 时给个导航, 而不是 404 ----
@app.get("/", include_in_schema=False)
def root():
    """给浏览器/新人一个入口, 真正的接口文档在 /docs。"""
    return ok(
        {
            "name": "居家老人监测系统 API",
            "version": app.version,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": "/health",
            "auth": "/api/auth/login",
            "device": "/api/device/heartbeat",
        },
        msg="服务已启动, 接口文档请打开 /docs",
    )


def _port_available(port: int) -> bool:
    """试探端口能不能绑定(不设 SO_REUSEADDR, 避免 Windows 上误判为可用)。"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _pick_port(preferred: int, span: int = 20) -> int:
    """优先用 preferred, 被占用就顺延找下一个空闲端口(最多找 span 个)。"""
    for port in range(preferred, preferred + span + 1):
        if _port_available(port):
            return port
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))  # 全被占就让系统随机分一个
        return s.getsockname()[1]


if __name__ == "__main__":
    import os

    import uvicorn

    # ---- 直接运行即可: PyCharm 里点 Run main.py, 或命令行 python main.py ----
    # 1) 默认不开 reload: reload 会额外起一个子进程, PyCharm 点停止时容易残留,
    #    残留进程占着端口, 下次启动就会报 WinError 10013 / 地址已被占用。
    #    需要热重载时再设环境变量 RELOAD=1。
    # 2) 5000 被别的进程占用(例如上一次没关干净的实例)时自动顺延到 5001/5002...,
    #    并在控制台把实际地址打印出来, 不需要你手动改端口。
    preferred = int(os.getenv("PORT", "5000"))
    port = _pick_port(preferred)
    reload_mode = os.getenv("RELOAD", "0") == "1"

    print("=" * 64, flush=True)
    print("  居家老人监测系统 API 已启动", flush=True)
    print(f"  接口文档(点这个最省事): http://127.0.0.1:{port}/docs", flush=True)
    print(f"  健康检查:                http://127.0.0.1:{port}/health", flush=True)
    if port != preferred:
        print(f"  注意: 端口 {preferred} 被占用或不可用, 已自动改用 {port}", flush=True)
    if reload_mode:
        print("  热重载: 已开启(RELOAD=1), 停止时请确认端口已释放", flush=True)
    print("  停止: 在这个窗口按 Ctrl+C, 或点 PyCharm 的停止按钮", flush=True)
    print("=" * 64, flush=True)

    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=reload_mode)

