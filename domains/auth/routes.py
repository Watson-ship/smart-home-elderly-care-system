"""认证接口。

现在是空壳, 后面写:
- POST /api/auth/login       登录, 返回 token
- POST /api/auth/register    注册(老人/家属/社康)
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/auth", tags=["认证"])
