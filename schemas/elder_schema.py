"""老人档案相关请求/响应"""
from pydantic import BaseModel


class ElderCreateReq(BaseModel):
    """新增老人档案"""
    elder_name: str
    gender: int | None = None
    age: int | None = None
    phone: str | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


class ElderUpdateReq(BaseModel):
    """编辑老人档案 (所有字段可选, 传了就改)"""
    elder_name: str | None = None
    gender: int | None = None
    age: int | None = None
    phone: str | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


class ElderResp(BaseModel):
    """老人档案响应"""
    id: int
    elder_name: str
    gender: int | None = None
    age: int | None = None
    phone: str | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    model_config = {"from_attributes": True}
