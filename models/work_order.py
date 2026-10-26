"""社康工单表: 派单 -> 处置 -> 归档"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, text

from db.base import Base


class WorkOrder(Base):
    __tablename__ = "work_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, nullable=False, unique=True, comment="逻辑外键 alert.id: 一条告警一张工单")
    elder_id = Column(Integer, nullable=False, comment="逻辑外键 elder.id: 老人")
    order_status = Column(Enum("pending", "processing", "archived"), nullable=False, default="pending", comment="pending待派单/processing处置中/archived已归档")
    handler_id = Column(Integer, comment="逻辑外键 user.id: 处理社工")
    handle_content = Column(Text, comment="处置记录内容")
    assign_time = Column(DateTime, comment="派单时间")
    archive_time = Column(DateTime, comment="归档时间")
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
