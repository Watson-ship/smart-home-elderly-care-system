"""数据库引擎和 Session 工厂。 engine 和 SessionLocal 在 main.py 启动时才创建, 避免模块 import 时就去连数据库(那时候配置可能还没加载好)。
用法 (FastAPI 依赖注入):
    from db.session import SessionLocal
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from infrastructure.security.jwt_tool import decode_token
from models.user import User

engine = None
SessionLocal = None


def init_session(database_url: str) -> None:
    """根据连接串创建 engine 和 SessionLocal, 在 main.py 启动时调用。"""
    global engine, SessionLocal
    engine = create_engine(database_url, pool_pre_ping=True, echo=False)
    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )


def get_db():
    """FastAPI 依赖注入: 每次请求一个 Session, 用完自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# JWT鉴权依赖
# 用 HTTPBearer 而不是 OAuth2PasswordBearer: 我们的 /api/auth/login 收的是 JSON,
# Swagger 的 Authorize 用 HTTPBearer 时只需要粘贴 token 本身, 联调更方便。
# auto_error=False 是为了自己统一抛 401(而不是 FastAPI 默认的 403)。
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="先调 POST /api/auth/login 拿 token, 这里粘贴纯 token(不要加 Bearer 前缀)",
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """接口依赖: 解析Bearer Token, 再按 user_id 查库返回 User 实体。
     返回实体(而不是 token 里的 payload), 原因: elder_id 不放进 token,
     家属重新绑定老人后立刻生效, 也避免前端伪造 elder_id 越权。
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="未登录或缺少 token, 请先调用 POST /api/auth/login",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    user = db.query(User).filter(User.id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")
    return user
