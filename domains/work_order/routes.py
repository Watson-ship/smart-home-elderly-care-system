"""社康工单 HTTP 接口"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.common_schema import BaseResp, ok
from domains.work_order import service
from domains.work_order.schema import WorkOrderResp, AssignReq, HandleReq

# 注意这里保留了你截图里的 work-order (带连字符)
router = APIRouter(prefix="/api/work-order", tags=["社康-工单看板"])

@router.get("", response_model=BaseResp[list[WorkOrderResp]], summary="工单列表(按状态过滤)")
def list_orders(
    status: str = Query(None, description="状态过滤(pending/processing/archived)"),
    db: Session = Depends(get_db)
):
    orders = service.get_order_list(db, status)
    return ok([WorkOrderResp.model_validate(o) for o in orders])

@router.post("/{order_id}/assign", response_model=BaseResp[WorkOrderResp], summary="工单派单")
def assign(order_id: int, data: AssignReq, db: Session = Depends(get_db)):
    order = service.assign_order(db, order_id, data)
    return ok(WorkOrderResp.model_validate(order))

@router.post("/{order_id}/handle", response_model=BaseResp[WorkOrderResp], summary="填写处置记录")
def handle(order_id: int, data: HandleReq, db: Session = Depends(get_db)):
    order = service.handle_order(db, order_id, data)
    return ok(WorkOrderResp.model_validate(order))

@router.post("/{order_id}/archive", response_model=BaseResp[WorkOrderResp], summary="工单归档")
def archive(order_id: int, db: Session = Depends(get_db)):
    order = service.archive_order(db, order_id)
    return ok(WorkOrderResp.model_validate(order))