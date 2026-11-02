from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from .model import MedicinePlan
from models.medicine_record import MedicineRecord
from .schema import MedicinePlanCreate, MedicinePlanUpdate, MedicinePlanSchema, MedicineRecordCreate, MedicineRecordSchema


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

    # 逻辑外键：先删该计划下的服药记录，再删计划（顺序反了会留脏数据）
    db.query(MedicineRecord).filter(MedicineRecord.plan_id == plan_id).delete()
    db.delete(plan)
    db.commit()


def create_medicine_record(db: Session, record_in: MedicineRecordCreate, elder_id: int):
    """老人确认服药：插 medicine_record（plan_id + 今天 + taken/untaken）"""
    plan = db.query(MedicinePlan).filter(MedicinePlan.id == record_in.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="用药计划不存在")
    if plan.elder_id != elder_id:
        raise HTTPException(status_code=403, detail="无权限操作该计划")

    db_record = MedicineRecord(
        plan_id=record_in.plan_id,
        elder_id=elder_id,
        remind_date=date.today(),
        take_result=record_in.take_result
    )
    db.add(db_record)
    try:
        db.commit()
    except IntegrityError:
        # 唯一索引 uk_plan_date 挡住重复确认
        db.rollback()
        raise HTTPException(status_code=400, detail="今天已确认过该服药计划")
    db.refresh(db_record)

    d = {
        "id": db_record.id,
        "plan_id": db_record.plan_id,
        "elder_id": db_record.elder_id,
        "remind_date": db_record.remind_date.strftime("%Y-%m-%d") if db_record.remind_date else None,
        "take_result": db_record.take_result,
        "record_time": db_record.record_time.strftime("%Y-%m-%d %H:%M:%S") if db_record.record_time else None
    }
    return MedicineRecordSchema(**d)


def get_medicine_record_list(db: Session, elder_id: int):
    """查看服药记录，按日期倒序"""
    record_list = db.query(MedicineRecord).filter(
        MedicineRecord.elder_id == elder_id
    ).order_by(MedicineRecord.remind_date.desc(), MedicineRecord.id.desc()).all()
    res = []
    for item in record_list:
        d = {
            "id": item.id,
            "plan_id": item.plan_id,
            "elder_id": item.elder_id,
            "remind_date": item.remind_date.strftime("%Y-%m-%d") if item.remind_date else None,
            "take_result": item.take_result,
            "record_time": item.record_time.strftime("%Y-%m-%d %H:%M:%S") if item.record_time else None
        }
        res.append(MedicineRecordSchema(**d))
    return res
