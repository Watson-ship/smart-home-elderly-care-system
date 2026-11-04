from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

class WorkOrderResp(BaseModel):
    id: int
    elder_id: int
    alert_id: Optional[int] = None
    # 模型里字段名是 order_status, 对外仍叫 status(前端已按 status 开发)
    status: str = Field(validation_alias="order_status")
    handler_id: Optional[int] = None
    handle_content: Optional[str] = None
    assign_time: Optional[datetime] = None
    archive_time: Optional[datetime] = None
    create_time: Optional[datetime] = None

    class Config:
        from_attributes = True

class AssignReq(BaseModel):
    handler_id: int = Field(..., description="派单给哪个社康人员")

class HandleReq(BaseModel):
    handle_content: str = Field(..., description="处置记录")