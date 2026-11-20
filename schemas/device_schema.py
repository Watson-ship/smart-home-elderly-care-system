"""摄像头设备相关请求/响应。

Owner: Person A (硬件方向)
    - 手动注册 / 心跳上报 / 视频片段上传 / 跌倒截图上传 / 提交视频离线检测 / 设备绑定
Person B 后续在本文件追加: 设备列表、实时画面查看等 schema。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceRegisterReq(BaseModel):
    """手动注册设备请求"""
    device_sn: Optional[str] = Field(
        None, min_length=1, max_length=64,
        description="设备序列号; 留空则由服务端自动生成(推荐)",
    )
    device_name: str = Field(..., min_length=1, max_length=100, description="设备名称, 如 客厅摄像头")
    hardware_id: Optional[str] = Field(
        None, max_length=128,
        description="设备硬件指纹; 同一台设备重复注册时直接返回原编号, 不会产生多个序号",
    )


class DeviceRegisterResp(BaseModel):
    """手动注册设备响应"""
    device_sn: str
    device_name: str
    status: str
    elder_id: Optional[int] = None
    generated: bool = Field(False, description="编号是否为服务端自动生成")


class DeviceItem(BaseModel):
    """设备列表里的一台设备"""
    device_sn: str
    device_name: str
    elder_id: Optional[int] = None
    elder_name: Optional[str] = None
    status: str
    last_online_time: Optional[datetime] = None


class DeviceUnbindReq(BaseModel):
    """解绑设备"""
    device_sn: str = Field(..., min_length=1, max_length=64, description="设备序列号")


class HeartbeatReq(BaseModel):
    """设备心跳请求"""
    device_sn: str = Field(..., min_length=1, max_length=64, description="设备序列号")


class HeartbeatResp(BaseModel):
    """设备心跳响应"""
    device_sn: str
    status: str
    last_online_time: datetime


class VideoUploadResp(BaseModel):
    """设备上传视频片段响应"""
    device_sn: str
    file_path: str
    file_url: str
    size: int
    auto_detect: Optional[bool] = Field(
        None, description="是否已把这段视频排进后台跌倒检测(检测结果请查看 /stream 目录或 alert 表)"
    )


class StreamUploadResp(BaseModel):
    """设备上传跌倒截图响应"""
    device_sn: str
    file_path: str
    file_url: str
    size: int
    alert_id: Optional[int] = None
    elder_id: Optional[int] = None


class FrameUploadResp(BaseModel):
    """设备上传一帧实时画面响应(只进内存, 不落盘、不建告警)"""
    device_sn: str
    size: int
    viewers: int = Field(0, description="当前正在看这台设备实时画面的人数")
    server_time: datetime = Field(..., description="服务端收到这一帧的时间")


class DetectedShot(BaseModel):
    """离线检测视频时截下来的一个跌倒帧"""
    event_id: str
    frame_index: int
    time_ms: int
    conf: float
    box: list[int]
    file_path: Optional[str] = None
    file_url: Optional[str] = None
    alert_id: Optional[int] = None


class DetectResp(BaseModel):
    """提交视频做跌倒检测的响应"""
    device_sn: str
    frames_processed: int
    fps: float
    infer_every: int
    fall_events: int
    elapsed_ms: int
    video_path: Optional[str] = Field(None, description="上传的原始视频保存位置")
    video_url: Optional[str] = Field(None, description="原始视频可直接访问的地址")
    screenshots: list[DetectedShot] = []


class BindReq(BaseModel):
    """绑定设备与老人"""
    device_sn: str = Field(..., min_length=1, max_length=64, description="设备序列号(内部编号, 由设备端上报)")
    elder_id: int = Field(..., gt=0, description="要绑定的老人 id")
    device_name: Optional[str] = Field(
        None, min_length=1, max_length=100,
        description="家属给设备起的昵称, 如 客厅 / 卧室; 不填保留原名",
    )


class DeviceRenameReq(BaseModel):
    """给设备改昵称"""
    device_sn: str = Field(..., min_length=1, max_length=64, description="设备序列号(内部编号)")
    device_name: str = Field(..., min_length=1, max_length=100, description="新昵称, 如 客厅")


class BindResp(BaseModel):
    """绑定结果"""
    device_sn: str
    device_name: str
    elder_id: int
