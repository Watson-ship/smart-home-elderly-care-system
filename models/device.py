"""摄像头设备表"""
from sqlalchemy import Column, Integer, String, DateTime, Enum, text

from db.base import Base


class Device(Base):
    __tablename__ = "device"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_sn = Column(String(64), nullable=False, unique=True, comment="设备序列号(上报身份标识)")
    device_name = Column(String(100), nullable=False, comment="设备名称")
    elder_id = Column(Integer, comment="逻辑外键 elder.id: 绑定的老人")
    status = Column(Enum("online", "offline"), nullable=False, default="offline", comment="在线状态")
    last_online_time = Column(DateTime, comment="最后在线时间(摄像头定期上报, 超时置offline)")
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
