# 老人档案领域
from pydantic import BaseModel, Field
from typing import Optional

class ElderCreateReq(BaseModel):
    name: str = Field(..., description="老人姓名")
    gender: Optional[str] = Field(None, description="性别")
    age: Optional[int] = Field(None, description="年龄")
    phone: Optional[str] = Field(None, description="联系电话")
    address: Optional[str] = Field(None, description="家庭住址")

class ElderUpdateReq(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class ElderResp(BaseModel):
    id: int
    name: str
    gender: Optional[str]
    age: Optional[int]
    phone: Optional[str]
    address: Optional[str]

    class Config:
        from_attributes = True