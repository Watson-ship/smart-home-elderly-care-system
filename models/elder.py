"""老人档案表"""
from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, text

from db.base import Base


class Elder(Base):
    __tablename__ = "elder"

    id = Column(Integer, primary_key=True, autoincrement=True)
    elder_name = Column(String(50), nullable=False, comment="老人姓名")
    gender = Column(SmallInteger, comment="性别 0-女 1-男")
    age = Column(Integer, comment="年龄")
    phone = Column(String(20), comment="老人联系电话")
    address = Column(String(200), comment="住址")
    emergency_contact_name = Column(String(50), comment="紧急联系人姓名")
    emergency_contact_phone = Column(String(20), comment="紧急联系人电话")
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
