"""工单接口。

后面写:
- POST /api/work-order/assign        社康派单
- POST /api/work-order/{id}/handle   填写处置记录
- POST /api/work-order/{id}/archive  归档
- GET  /api/work-order               工单列表(按状态/社工筛选)
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/work-order", tags=["工单"])
