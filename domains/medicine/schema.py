from pydantic import BaseModel, Field
from typing import Literal

class MedicinePlanCreate(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=100, description="药品名称，最长100字符")
    take_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$", description="服药时间，格式 HH:MM:SS")
    cycle: Literal["daily", "two_day"] = Field(description="周期：daily每天 / two_day隔天")

class MedicinePlanUpdate(MedicinePlanCreate):
    status: Literal[0, 1] = Field(description="状态：1启用，0停用")

class MedicineRecordCreate(BaseModel):
    plan_id: int = Field(gt=0, description="用药计划ID")
    take_result: Literal["taken", "untaken"] = Field(description="taken已服 / untaken未服")

class MedicineRecordSchema(BaseModel):
    id: int
    plan_id: int
    elder_id: int
    remind_date: str
    take_result: str
    record_time: str | None

    class Config:
        from_attributes = True


class MedicinePlanSchema(BaseModel):
    id: int
    elder_id: int
    medicine_name: str
    take_time: str | None
    cycle: str
    status: int

    class Config:
        from_attributes = True


# ---------------- 阶段 3: 分页 / 统计 ----------------


class MedicinePlanPage(BaseModel):
    """用药计划分页结果"""
    total: int = Field(description="符合条件的总条数")
    page: int = Field(description="当前页码, 从 1 开始")
    size: int = Field(description="每页条数")
    pages: int = Field(description="总页数")
    items: list[MedicinePlanSchema] = Field(description="当前页数据")


class DailyTakenStat(BaseModel):
    """某一天的服药情况"""
    date: str = Field(description="日期 YYYY-MM-DD")
    taken: int = Field(description="已服条数")
    untaken: int = Field(description="未服条数")
    total: int = Field(description="当天确认总条数")
    rate: float = Field(description="当天按时服药率(百分比, 保留1位小数)")


class MedicineStatsResp(BaseModel):
    """近 N 天按时服药率统计(前端图表用)"""
    elder_id: int
    start_date: str = Field(description="统计起始日期 YYYY-MM-DD")
    end_date: str = Field(description="统计结束日期 YYYY-MM-DD")
    days: int = Field(description="统计天数")
    total: int = Field(description="确认总条数")
    taken: int = Field(description="已服条数")
    untaken: int = Field(description="未服条数")
    rate: float = Field(description="整体按时服药率(百分比, 保留1位小数)")
    daily: list[DailyTakenStat] = Field(description="按天明细, 无记录的日期也返回(值为0)")