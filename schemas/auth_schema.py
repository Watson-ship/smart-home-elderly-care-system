"""认证相关: 登录/注册"""
from pydantic import BaseModel


class LoginReq(BaseModel):
    username: str
    password: str


class LoginResp(BaseModel):
    """登录成功返回 token + 用户基本信息"""
    token: str
    user_id: int
    role: str
    elder_id: int | None = None
