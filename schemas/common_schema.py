from pydantic import BaseModel
from typing import Generic, TypeVar, Optional

T = TypeVar("T")

class BaseResp(BaseModel, Generic[T]):
    code: int = 0
    msg: str = "ok"
    data: Optional[T] = None

def ok(data: T = None, msg: str = "ok") -> BaseResp[T]:
    return BaseResp(code=0, msg=msg, data=data)