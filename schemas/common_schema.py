"""通用响应: 全项目统一返回结构, 前端只认 code / msg / data。

约定 (三个人都按这个写, 不要各自造格式):
    成功: {"code": 0, "msg": "ok", "data": {...}}      # data 是各接口自己的响应模型
    失败: {"code": 404, "msg": "老人 999 不存在", "data": null}
    code: 0 表示成功, 非 0 直接用 HTTP 状态码 (400 参数错 / 404 不存在 / 500 服务端错误)

路由写法:
    @router.post("/x", response_model=BaseResp[SomeResp], summary="...")
    def x(...):
        return ok(SomeResp(...))        # 成功
        raise HTTPException(404, "...")  # 失败, 由 main.py 的异常处理器自动包成统一结构
"""
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class BaseResp(BaseModel, Generic[T]):
    """统一响应格式。

    BaseResp[HeartbeatResp] 在 Swagger 里能完整展开 data 的字段,
    所以 response_model 一定要写成带泛型参数的版本。
    """
    code: int = 0
    msg: str = "ok"
    data: Optional[T] = None


def ok(data: object = None, msg: str = "ok") -> dict:
    """成功响应快捷写法: return ok(XxxResp(...))。"""
    return {"code": 0, "msg": msg, "data": data}


class HealthResp(BaseModel):
    """健康检查响应"""
    status: str
