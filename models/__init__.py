"""模型包: 7 张表, 一文件一表, 贫血模型(只有字段没有方法)。

import 习惯用法: from models import Elder, User, Device ...
"""
from models.elder import Elder
from models.user import User
from models.device import Device
from models.medicine_plan import MedicinePlan
from models.medicine_record import MedicineRecord
from models.alert import Alert
from models.work_order import WorkOrder

__all__ = [
    "Elder",
    "User",
    "Device",
    "MedicinePlan",
    "MedicineRecord",
    "Alert",
    "WorkOrder",
]
