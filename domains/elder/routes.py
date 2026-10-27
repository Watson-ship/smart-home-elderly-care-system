"""老人档案 HTTP 接口 —— 社康工作人员用。

现在是空壳, 后面写:
- POST   /api/elder          新增老人档案
- PUT    /api/elder/{id}     编辑老人档案
- GET    /api/elder          查询老人档案(列表/按条件)
- GET    /api/elder/{id}     查询单个档案
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/elder", tags=["老人档案"])

# @router.post("", summary="新增老人档案")
# async def create():
#     ...
