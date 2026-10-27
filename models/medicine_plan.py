"""用药计划表(家属维护)"""
from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Time, Enum, text

from db.base import Base


class MedicinePlan(Base):
    __tablename__ = "medicine_plan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    elder_id = Column(Integer, nullable=False, comment="逻辑外键 elder.id: 老人")
    medicine_name = Column(String(100), nullable=False, comment="药品名")
    take_time = Column(Time, nullable=False, comment="每天几点服药")
    cycle = Column(Enum("daily", "two_day"), nullable=False, default="daily", comment="周期: daily每天 / two_day隔天")
    status = Column(SmallInteger, nullable=False, default=1, comment="1启用 0停用")
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
