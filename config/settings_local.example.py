"""本地配置模板。

用法：
    1. 复制本文件为同目录下的 settings_local.py
    2. 把下面的「你的密码」改成你自己的 MySQL 密码
    3. settings_local.py 已被 .gitignore 忽略，不会被提交

如果密码里有 @ : / # 等特殊字符，需要 URL 编码（例如 @ 写成 %40）。
"""

DATABASE_URL = "mysql+pymysql://root:你的密码@127.0.0.1:3306/elderly_care?charset=utf8mb4&serverTimezone=Asia/Shanghai"
