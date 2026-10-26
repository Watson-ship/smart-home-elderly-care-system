"""摄像头设备接口。

后面写:
- POST /api/device/heartbeat     设备心跳上报(更新 last_online_time)
- POST /api/device/stream        上传视频流地址 / 开始推流
- POST /api/device/{id}/bind     家属绑定老人与摄像头
- GET  /api/device                家属查看绑定的摄像头列表
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/device", tags=["摄像头设备"])
