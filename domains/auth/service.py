"""认证业务逻辑: 注册、登录校验、JWT 签发。

Owner: Person A (硬件方向)
密码哈希/校验、token 签发与解析都复用 B 的 infrastructure/security 模块,
本文件只做业务串联 (查库 / 判重 / 抛异常给路由层翻译成 HTTP 状态码)。
"""
from sqlalchemy.orm import Session

from infrastructure.security.jwt_tool import create_token
from infrastructure.security.password import hash_password, verify_password
from models import Elder, User


def find_user(db: Session, username: str) -> User | None:
    """按用户名查账号。"""
    return db.query(User).filter(User.username == username).first()


def register_user(
    db: Session,
    username: str,
    password: str,
    role: str,
    elder_id: int | None = None,
    phone: str | None = None,
) -> User:
    """注册账号。

    - 用户名唯一: 已存在抛 ValueError (路由层 -> 400)
    - 填了 elder_id 就要保证老人存在, 否则抛 LookupError (路由层 -> 404)
    - 密码在这里哈希后入库, 数据库里永远不存明文
    """
    if find_user(db, username) is not None:
        raise ValueError(f"用户名 {username} 已被注册, 请换一个")

    if elder_id is not None and db.get(Elder, elder_id) is None:
        raise LookupError(f"老人 {elder_id} 不存在")

    user = User(
        username=username,
        password=hash_password(password),
        role=role,
        elder_id=elder_id,
        phone=phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, username: str, password: str) -> User:
    """登录校验: 用户名 + 密码。

    用户不存在和密码不对都抛同一个 LookupError("用户名或密码错误"),
    避免接口返回不同提示被用来枚举账号。路由层统一转成 401。
    """
    user = find_user(db, username)
    if user is None or not verify_password(password, user.password):
        raise LookupError("用户名或密码错误")
    return user


def issue_token(user: User) -> str:
    """给登录成功的用户签 JWT(token 里只有 user_id 和 role)。"""
    return create_token(user.id, user.role)
