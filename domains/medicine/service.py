from sqlalchemy.orm import Session
from fastapi import HTTPException
from .model import MedicinePlan
from .schema import MedicinePlanCreate, MedicinePlanUpdate, MedicinePlanSchema


def get_medicine_plan_list(db: Session, elder_id: int):
    """按elder_id查询用药计划，权限隔离"""
    plan_list = db.query(MedicinePlan).filter(MedicinePlan.elder_id == elder_id).all()
    res = []
    for item in plan_list:
        d = {
            "id": item.id,
            "elder_id": item.elder_id,
            "medicine_name": item.medicine_name,
            "take_time": item.take_time.strftime("%H:%M:%S") if item.take_time else None,
            "cycle": item.cycle,
            "status": item.status
        }
        res.append(MedicinePlanSchema(**d))
    return res


def create_medicine_plan(db: Session, elder_id: int, plan_in: MedicinePlanCreate):
    """新增用药计划，自动绑定当前家属对应的elder_id"""
    from datetime import time
    hh, mm, ss = map(int, plan_in.take_time.split(":"))
    take_time_obj = time(hour=hh, minute=mm, second=ss)

    db_plan = MedicinePlan(
        elder_id=elder_id,
        medicine_name=plan_in.medicine_name,
        take_time=take_time_obj,
        cycle=plan_in.cycle
    )
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)

    d = {
        "id": db_plan.id,
        "elder_id": db_plan.elder_id,
        "medicine_name": db_plan.medicine_name,
        "take_time": db_plan.take_time.strftime("%H:%M:%S") if db_plan.take_time else None,
        "cycle": db_plan.cycle,
        "status": db_plan.status
    }
    return MedicinePlanSchema(**d)


def update_medicine_plan(db: Session, plan_id: int, plan_in: MedicinePlanUpdate, elder_id: int):
    """编辑用药计划，校验归属权限"""
    plan = db.query(MedicinePlan).filter(MedicinePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="用药计划不存在")
    if plan.elder_id != elder_id:
        raise HTTPException(status_code=403, detail="无权限操作该计划")

    from datetime import time
    hh, mm, ss = map(int, plan_in.take_time.split(":"))
    take_time_obj = time(hour=hh, minute=mm, second=ss)

    plan.medicine_name = plan_in.medicine_name
    plan.take_time = take_time_obj
    plan.cycle = plan_in.cycle
    plan.status = plan_in.status
    db.commit()
    db.refresh(plan)

    d = {
        "id": plan.id,
        "elder_id": plan.elder_id,
        "medicine_name": plan.medicine_name,
        "take_time": plan.take_time.strftime("%H:%M:%S") if plan.take_time else None,
        "cycle": plan.cycle,
        "status": plan.status
    }
    return MedicinePlanSchema(**d)


def delete_medicine_plan(db: Session, plan_id: int, elder_id: int):
    """删除用药计划，校验归属权限"""
    plan = db.query(MedicinePlan).filter(MedicinePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="用药计划不存在")
    if plan.elder_id != elder_id:
        raise HTTPException(status_code=403, detail="无权限操作该计划")

    db.delete(plan)
    db.commit()
