"""工单业务逻辑。"""
from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.work_order import WorkOrder
from models.alert import Alert  # 需要联动修改 Alert 的状态
from domains.work_order.schema import AssignReq, HandleReq
from datetime import datetime


def get_order_list(db: Session, status: str = None):
    query = db.query(WorkOrder)
    if status:
        query = query.filter(WorkOrder.status == status)
    return query.all()


def assign_order(db: Session, order_id: int, data: AssignReq):
    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        raise HTTPException(404, "工单不存在")
    order.handler_id = data.handler_id
    order.status = "processing"
    # order.assign_time = datetime.now() # 如果你表里有这个字段就加上
    db.commit()
    db.refresh(order)
    return order


def handle_order(db: Session, order_id: int, data: HandleReq):
    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        raise HTTPException(404, "工单不存在")
    order.handle_content = data.handle_content
    # order.status = "handled" # 如果处置后要改状态
    db.commit()
    db.refresh(order)
    return order


def archive_order(db: Session, order_id: int):
    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        raise HTTPException(404, "工单不存在")
    order.status = "archived"
    # order.archive_time = datetime.now()

    # 逻辑要点：归档时，把关联的 alert 状态也改了
    if order.alert_id:
        alert = db.query(Alert).filter(Alert.id == order.alert_id).first()
        if alert:
            alert.is_handled = 1  # 1表示已处置

    db.commit()
    db.refresh(order)
    return order