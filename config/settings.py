# 统一配置模板（会上传到 Git）

# 尝试导入本地私有配置
try:
    from .settings_local import DATABASE_URL
except ImportError:
    # 如果队友没有建 settings_local.py，就用这个默认占位符，防止代码报错
    DATABASE_URL = "mysql+pymysql://root:password@127.0.0.1:3306/elderly_care?charset=utf8mb4&serverTimezone=Asia/Shanghai"