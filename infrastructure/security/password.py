from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw_pwd: str) -> str:
    """对明文密码做bcrypt哈希加密"""
    return pwd_context.hash(raw_pwd)


def verify_password(raw_pwd: str, hashed_pwd: str) -> bool:
    """校验：输入明文密码，和数据库存储的密文比对，返回True/False"""
    return pwd_context.verify(raw_pwd, hashed_pwd)
