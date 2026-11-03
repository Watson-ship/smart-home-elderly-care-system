"""密码哈希与校验。

Owner: Person B (家属/安全方向)
补充说明 (Person A): 阶段 1 注册/登录接口会调用这里的 hash_password / verify_password。
db/seed.py 的演示账号用的是 werkzeug generate_password_hash 生成的 scrypt 哈希，
和本项目新注册账号用的 bcrypt 格式不一样，所以 verify_password 两种都要认，
否则种子账号(admin/123456)会登不进去。
"""
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw_pwd: str) -> str:
    """对明文密码做bcrypt哈希加密"""
    return pwd_context.hash(raw_pwd)


def _verify_werkzeug_scrypt(raw_pwd: str, hashed_pwd: str) -> bool:
    """校验 werkzeug 的 scrypt 哈希, 格式: scrypt:32768:8:1$salt$hexdigest。

    werkzeug 的默认参数就是 n=32768, r=8, p=1 (格式里没写参数时按默认取)。
    """
    import hashlib
    import hmac

    try:
        method, salt, digest = hashed_pwd.split("$", 2)
        name, *params = method.split(":")
        if name != "scrypt":
            return False
        n, r, p = (int(x) for x in (params + ["32768", "8", "1"])[:3])
        # scrypt 需要 128*n*r 字节内存, OpenSSL 默认上限只有 32MB,
        # n=32768/r=8 刚好卡在边界会报 "memory limit exceeded", 所以显式放大上限
        maxmem = 128 * n * r + 1024 * 1024
        calc = hashlib.scrypt(
            raw_pwd.encode(), salt=salt.encode(), n=n, r=r, p=p, maxmem=maxmem
        ).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, TypeError, MemoryError):
        return False


def verify_password(raw_pwd: str, hashed_pwd: str) -> bool:
    """校验：输入明文密码，和数据库存储的密文比对，返回True/False。

    兼容两种格式:
        - 本系统注册接口写入的 bcrypt 哈希 ($2b$...)
        - db/seed.py 的演示账号用的 werkzeug scrypt 哈希 (scrypt:32768:8:1$salt$hash)

    任何无法识别的哈希、空密码都当作校验失败, 不抛异常(避免登录接口 500)。
    """
    if not raw_pwd or not hashed_pwd:
        return False
    if hashed_pwd.startswith("scrypt:"):
        return _verify_werkzeug_scrypt(raw_pwd, hashed_pwd)
    try:
        return pwd_context.verify(raw_pwd, hashed_pwd)
    except (ValueError, TypeError):
        return False
