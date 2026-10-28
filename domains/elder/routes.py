"""老人档案 HTTP 接口 —— 社康工作人员用。

现在实现：
- POST /api/elder       新增老人档案
- PUT  /api/elder/{id}  编辑老人档案
- GET  /api/elder       查询老人档案(列表/按条件)
- GET  /api/elder/{id}  查询单个档案
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.common_schema import BaseResp, ok
from domains.elder import service
from domains.elder.schema import ElderCreateReq, ElderUpdateReq, ElderResp

router = APIRouter(prefix="/api/elder", tags=["老人档案"])

@router.get("", response_model=BaseResp[dict], summary="查询老人列表")
def list_elders(
    keyword: str = Query(None, description="姓名模糊查询"),
    page: int = Query(1, description="页码"),
    size: int = Query(10, description="每页数量"),
    db: Session = Depends(get_db)
):
    result = service.get_elder_list(db, keyword, page, size)
    return ok({
        "total": result["total"],
        "items": [ElderResp.model_validate(item).model_dump() for item in result["items"]]
    })

@router.get("/{elder_id}", response_model=BaseResp[ElderResp], summary="查询单个老人")
def get_elder(elder_id: int, db: Session = Depends(get_db)):
    elder = service.get_elder_by_id(db, elder_id)
    return ok(ElderResp.model_validate(elder))

@router.post("", response_model=BaseResp[ElderResp], summary="新增老人档案")
def add_elder(data: ElderCreateReq, db: Session = Depends(get_db)):
    elder = service.create_elder(db, data)
    return ok(ElderResp.model_validate(elder))

@router.put("/{elder_id}", response_model=BaseResp[ElderResp], summary="编辑老人档案")
def edit_elder(elder_id: int, data: ElderUpdateReq, db: Session = Depends(get_db)):
    elder = service.update_elder(db, elder_id, data)
    return ok(ElderResp.model_validate(elder))