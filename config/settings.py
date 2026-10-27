"""统一配置: 数据库连接、密钥、AI 模型路径等基础设施配置。
优先级: 环境变量 > settings_local.py > 本文件默认值
使用方法: 复制本文件一份改名为 settings_local.py, 把 DATABASE_URL 改成你自己的密码。
         settings_local.py 已被 .gitignore 忽略, 不会上传。
"""
import importlib.util
import os

# ---------- 先尝试加载 settings_local.py (本地密码, 不上传) ----------
_LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings_local.py")
_LOCAL = None
if os.path.exists(_LOCAL_PATH):
    _spec = importlib.util.spec_from_file_location("settings_local", _LOCAL_PATH)
    _LOCAL = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_LOCAL)


def _local(key, default):
    """取值工具: 本地有就用本地, 否则用默认值。"""
    if _LOCAL and hasattr(_LOCAL, key):
        return getattr(_LOCAL, key)
    return default


# ---- 数据库 ----
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    _local(
        "DATABASE_URL",
        # TODO: 如果你没建 settings_local.py, 就把这里改成你自己的 MySQL 连接串
        # 格式: mysql+pymysql://用户名:密码@主机:端口/数据库名?charset=utf8mb4&serverTimezone=Asia/Shanghai
        # 密码里如果有 @ : / # 等特殊字符需要 URL 编码 (例如 @ 写成 %40)
        "mysql+pymysql://root:你的密码@127.0.0.1:3306/elderly_care?charset=utf8mb4&serverTimezone=Asia/Shanghai",
    ),
)

# ---- 安全(JWT) ----
SECRET_KEY = os.getenv("SECRET_KEY", _local("SECRET_KEY", "dev-secret-key-change-me"))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

# ---- 存储路径 ----
STORAGE_PATH = os.getenv("STORAGE_PATH", _local("STORAGE_PATH", "static/screenshots"))

# ---- AI 相关 ----
AI_MODEL_PATH = os.getenv("AI_MODEL_PATH", _local("AI_MODEL_PATH", "model/best.pt"))
AI_INFERENCE_TIMEOUT = float(os.getenv("AI_INFERENCE_TIMEOUT", _local("AI_INFERENCE_TIMEOUT", "3.0")))
STATIC_SECONDS_THRESHOLD = int(os.getenv("STATIC_SECONDS_THRESHOLD", _local("STATIC_SECONDS_THRESHOLD", "120")))

# ---- 告警 ----
SOS_CANCEL_WINDOW = int(os.getenv("SOS_CANCEL_WINDOW", _local("SOS_CANCEL_WINDOW", "30")))

# ---- 定时任务 ----
MEDICINE_CHECK_INTERVAL_MINUTES = int(os.getenv("MEDICINE_CHECK_INTERVAL_MINUTES", _local("MEDICINE_CHECK_INTERVAL_MINUTES", "1")))

# ---- 设备在线 ----
DEVICE_HEARTBEAT_TIMEOUT = int(os.getenv("DEVICE_HEARTBEAT_TIMEOUT", _local("DEVICE_HEARTBEAT_TIMEOUT", "90")))
