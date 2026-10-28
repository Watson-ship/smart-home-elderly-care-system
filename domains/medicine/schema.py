from pydantic import BaseModel
from datetime import time, datetime
from typing import Literal

class MedicinePlanSchema(BaseModel):
    id: int
    elder_id: int
    medicine_name: str
    take_time: time
    cycle: Literal["daily", "two_day"]
    status: int
    create_time: datetime

    class Config:
        from_attributes = True
