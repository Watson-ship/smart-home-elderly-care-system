"""用户表: 老人/家属/社康工作人员共用, 靠 role 区分"""
from sqlalchemy import Column, Integer, String, DateTime, Enum, text

from db.base import Base


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True, comment="登录账号")
    password = Column(String(255), nullable=False, comment="密码哈希(werkzeug generate_password_hash)")
    role = Column(Enum("elder", "family", "social"), nullable=False, comment="角色: elder/family/social")
    elder_id = Column(Integer, comment="逻辑外键 elder.id: 家属=绑定对象, 老人=本人, 社康为空")
    phone = Column(String(20), comment="手机号")
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
