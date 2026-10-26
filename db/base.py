"""SQLAlchemy 声明基类: 所有 ORM 模型都继承它。

放到 db/ 包里而不是 models/, 因为它是数据库基础设施的一部分,
和具体业务表结构无关。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有模型的父类, 原来 app/extensions.py 里的那个。"""
    pass
