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

# ---- 静态文件: 设备上报的画面、告警截图都从这里访问 ----
# 例: /static/stream/CAM‑SN‑001.jpg
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=5000, reload=True)

