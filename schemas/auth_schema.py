"""认证相关: 注册 / 登录 / 当前用户。

Owner: Person A (硬件方向) —— 阶段 1 的 3 个账号接口
    POST /api/auth/register  注册账号(老人/家属/社康)
    POST /api/auth/login     登录, 返回 JWT token
    GET  /api/auth/me        当前登录用户信息(需 Bearer token)
Person B 后续在本文件追加: 修改密码、角色权限等。
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

# 与 models/user.py 的 role 枚举保持一致
Role = Literal["elder", "family", "social"]


class RegisterReq(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=2, max_length=50, description="登录账号, 全表唯一")
    password: str = Field(..., min_length=6, max_length=64, description="明文密码, 6~64 位")
    role: Role = Field(..., description="角色: elder 老人 / family 家属 / social 社康")
    elder_id: Optional[int] = Field(
        None, gt=0, description="关联老人 id: 老人填本人, 家属填绑定对象, 社康可不填"
    )
    phone: Optional[str] = Field(None, max_length=20, description="手机号")


class RegisterResp(BaseModel):
    """注册结果"""
    user_id: int
    username: str
    role: str
    elder_id: Optional[int] = None


class LoginReq(BaseModel):
    username: str
    password: str


class LoginResp(BaseModel):
    """登录成功返回 token + 用户基本信息"""
    token: str
    user_id: int
    role: str
    elder_id: int | None = None


class MeResp(BaseModel):
    """当前登录用户信息"""
    id: int
    username: str
    role: str
    elder_id: Optional[int] = None
    phone: Optional[str] = None
