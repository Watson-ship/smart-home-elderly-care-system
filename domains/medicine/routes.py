"""用药接口。

后面写:
- POST   /api/medicine/plan          家属新增用药计划
- PUT    /api/medicine/plan/{id}     家属编辑用药计划
- DELETE /api/medicine/plan/{id}     家属删除用药计划
- GET    /api/medicine/plan          查看用药计划列表
- POST   /api/medicine/record        老人确认已服/未服
- GET    /api/medicine/record        查看服药记录
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/medicine", tags=["用药"])
