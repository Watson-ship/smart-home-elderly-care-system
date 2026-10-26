"""服药确认记录表(老人确认已服/未服)"""
from sqlalchemy import Column, Integer, String, DateTime, Date, Enum, UniqueConstraint, text

from db.base import Base


class MedicineRecord(Base):
    __tablename__ = "medicine_record"
    __table_args__ = (
        UniqueConstraint("plan_id", "remind_date", name="uk_plan_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, nullable=False, comment="逻辑外键 medicine_plan.id: 用药计划")
    elder_id = Column(Integer, nullable=False, comment="逻辑外键 elder.id: 老人")
    remind_date = Column(Date, nullable=False, comment="这剂药属于哪一天")
    take_result = Column(Enum("taken", "untaken"), nullable=False, comment="taken已服 / untaken未服")
    record_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="确认时间")
