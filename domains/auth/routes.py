"""认证接口。

阶段 1 (Person A):
    POST /api/auth/register  注册账号(老人/家属/社康)
    POST /api/auth/login     登录, 返回 JWT token
    GET  /api/auth/me        当前登录用户信息(需 Bearer token)

注意: 设备接口(domains/device)靠 device_sn 认身份, 不走这套登录;
      auth 的接口是给家属/老人/社康的 Web 端用的。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_current_user, get_db
from domains.auth import service
from models import User
from schemas.auth_schema import LoginReq, LoginResp, MeResp, RegisterReq, RegisterResp
from schemas.common_schema import BaseResp, ok

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=BaseResp[RegisterResp], summary="注册账号")
def register(req: RegisterReq, db: Session = Depends(get_db)):
    """注册老人/家属/社康账号。

    用户名全表唯一, 重复返回 400; 填了 elder_id 但老人不存在返回 404。
    密码用 bcrypt 哈希后入库, 响应里不返回密码。
    """
    try:
        user = service.register_user(
            db, req.username, req.password, req.role, req.elder_id, req.phone
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return ok(
        RegisterResp(
            user_id=user.id,
            username=user.username,
            role=user.role,
            elder_id=user.elder_id,
        )
    )


@router.post("/login", response_model=BaseResp[LoginResp], summary="登录")
def login(req: LoginReq, db: Session = Depends(get_db)):
    """用户名 + 密码换 token。

    成功返回 token(有效期 120 分钟)和 user_id/role/elder_id,
    之后前端请求受保护接口时带请求头 `Authorization: Bearer {token}`。
    用户不存在或密码错误都返回 401, 提示统一为"用户名或密码错误"。
    """
    try:
        user = service.authenticate(db, req.username, req.password)
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    token = service.issue_token(user)
    return ok(
        LoginResp(
            token=token,
            user_id=user.id,
            role=user.role,
            elder_id=user.elder_id,
        )
    )


@router.get("/me", response_model=BaseResp[MeResp], summary="当前登录用户")
def me(current_user: User = Depends(get_current_user)):
    """返回当前 token 对应的用户信息。

    token 缺失/伪造/过期都返回 401(由 db/session.py 的 get_current_user 与
    infrastructure/security/jwt_tool.py 抛出的 HTTPException 处理)。
    """
    return ok(
        MeResp(
            id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            elder_id=current_user.elder_id,
            phone=current_user.phone,
        )
    )
