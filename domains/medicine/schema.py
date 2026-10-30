from pydantic import BaseModel, Field
from typing import Literal

class MedicinePlanCreate(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=100, description="药品名称，最长100字符")
    take_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$", description="服药时间，格式 HH:MM:SS")
    cycle: Literal["daily", "two_day"] = Field(description="周期：daily每天 / two_day隔天")

class MedicinePlanUpdate(MedicinePlanCreate):
    status: Literal[0, 1] = Field(description="状态：1启用，0停用")

class MedicinePlanSchema(BaseModel):
    id: int
    elder_id: int
    medicine_name: str
    take_time: str | None
    cycle: str
    status: int

    class Config:
        from_attributes = True