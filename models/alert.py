"""告警表: AI跌倒/长时间静止 + 老人一键SOS"""
from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Enum, Index, text

from db.base import Base


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (
        Index("idx_elder_time", "elder_id", "create_time"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    elder_id = Column(Integer, nullable=False, comment="逻辑外键 elder.id: 老人")
    device_id = Column(Integer, comment="逻辑外键 device.id: 触发摄像头(SOS可能为空)")
    alert_type = Column(Enum("fall", "static", "sos"), nullable=False, comment="fall跌倒 / static静止 / sos求助")
    screenshot_path = Column(String(500), comment="告警截图相对路径")
    is_handled = Column(SmallInteger, nullable=False, default=0, comment="0未处置 1已处置")
    handled_by = Column(Integer, comment="逻辑外键 user.id: 处置人(家属或社康)")
    handle_time = Column(DateTime, comment="处置时间")
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="告警时间")
