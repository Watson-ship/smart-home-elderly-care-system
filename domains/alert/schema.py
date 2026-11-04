"""告警相关请求/响应模型。

Owner: Person A (阶段 2 的一键求助 + 我的告警)
    POST /api/alert/sos         发起一键求助(自动建工单)
    POST /api/alert/sos/cancel  取消求助
    GET  /api/alert/my          查看自己的告警
Person B 后续追加: 告警详情、标记已处置、AI 告警回调等。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SosReq(BaseModel):
    """一键求助请求: device_id 可空(SOS 可能是老人按按钮, 不一定来自摄像头)"""
    device_id: Optional[int] = Field(None, gt=0, description="触发设备 id, 可空")


class SosResp(BaseModel):
    """求助成功返回: 告警 + 自动生成的工单"""
    alert_id: int
    work_order_id: int
    elder_id: int
    elder_name: Optional[str] = None
    order_status: str = "pending"
    create_time: Optional[datetime] = None


class SosCancelResp(BaseModel):
    """取消求助结果"""
    cancelled: bool
    alert_id: Optional[int] = None
    work_order_id: Optional[int] = None
    message: str = "ok"


class AlertItem(BaseModel):
    """告警列表项"""
    id: int
    elder_id: int
    device_id: Optional[int] = None
    alert_type: str
    screenshot_path: Optional[str] = None
    screenshot_url: Optional[str] = None
    is_handled: int = 0
    handled_by: Optional[int] = None
    handle_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
