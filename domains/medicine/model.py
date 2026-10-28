from sqlalchemy import Column, Integer, String, Time
from db.base import Base

class MedicinePlan(Base):
    __tablename__ = "medicine_plan"

    id = Column(Integer, primary_key=True, index=True, comment="主键")
    elder_id = Column(Integer, nullable=False, comment="老人id")
    medicine_name = Column(String(100), nullable=False, comment="药品名称")
    take_time = Column(Time, nullable=False, comment="服药时间")
    cycle = Column(String(50), nullable=False, comment="周期：每天/隔天等")
    status = Column(Integer, default=1, comment="1启用 0停用")
