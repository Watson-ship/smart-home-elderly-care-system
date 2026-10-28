from pydantic import BaseModel, Field
from typing import Optional

# 新增时的请求参数
class ElderCreateReq(BaseModel):
    elder_name: str = Field(..., description="老人姓名")  # 名字改成了 elder_name
    gender: Optional[int] = Field(None, description="性别(例如:1男 2女)") # 改成 int
    age: Optional[int] = Field(None, description="年龄")
    phone: Optional[str] = Field(None, description="联系电话")
    address: Optional[str] = Field(None, description="家庭住址")
    emergency_contact_name: Optional[str] = Field(None, description="紧急联系人姓名")
    emergency_contact_phone: Optional[str] = Field(None, description="紧急联系人电话")

# 编辑时的请求参数
class ElderUpdateReq(BaseModel):
    elder_name: Optional[str] = None
    gender: Optional[int] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

# 响应参数
class ElderResp(BaseModel):
    id: int
    elder_name: str   # 这里也改成 elder_name
    gender: Optional[int]  # 这里也改成 int
    age: Optional[int]
    phone: Optional[str]
    address: Optional[str]
    emergency_contact_name: Optional[str]
    emergency_contact_phone: Optional[str]

    class Config:
        from_attributes = True