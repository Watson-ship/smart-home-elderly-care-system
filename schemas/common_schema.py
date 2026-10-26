"""通用响应: 所有接口统一返回这个结构, 前端解析方便。

课设简化版: 不搞多层嵌套, 用泛型 BaseResp[T] 就行。
"""
from typing import TypeVar, Optional

from pydantic import BaseModel

T = TypeVar("T")


class BaseResp(BaseModel):
    """统一响应格式。

    成功: {"code": 0, "msg": "ok", "data": ...}
    失败: {"code": 4001, "msg": "密码错误", "data": null}
    """
    code: int = 0
    msg: str = "ok"
    data: Optional[dict | list] = None


class HealthResp(BaseModel):
    """健康检查响应"""
    status: str
