from pydantic import BaseModel, Field
from typing import Optional

class WorkOrderResp(BaseModel):
    id: int
    elder_id: int
    alert_id: Optional[int] = None
    status: str
    handler_id: Optional[int] = None
    handle_content: Optional[str] = None
    # ... 加上你模型里有的其他字段

    class Config:
        from_attributes = True

class AssignReq(BaseModel):
    handler_id: int = Field(..., description="派单给哪个社康人员")

class HandleReq(BaseModel):
    handle_content: str = Field(..., description="处置记录")