from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

from db.session import engine
from db.base import Base
from schemas.common_schema import ok

app = FastAPI(title="居家老人监测系统")

# 统一异常处理：把 HTTPException 包装成 code/msg/data
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.detail, "data": None}
    )

# 启动时连库建表
@app.on_event("startup")
def startup():
    try:
        # 这里以后要 import 所有的 models，否则建表会漏
        # 比如: from models import user, elder, device, alert, medicine_plan, medicine_record, work_order
        Base.metadata.create_all(bind=engine)
        print(f"[启动] 数据库连接成功, 已自动建表")
    except Exception as e:
        print(f"[启动] 数据库连接失败: {e}")

# 健康检查接口
@app.get("/health")
def health():
    return ok({"status": "running"})

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=5000, reload=True)