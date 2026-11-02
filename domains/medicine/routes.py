"""用药接口。
- POST   /api/medicine/plans          家属新增用药计划
- PUT    /api/medicine/plans/{id}     家属编辑用药计划
- DELETE /api/medicine/plans/{id}     家属删除用药计划（先删该计划的服药记录）
- GET    /api/medicine/plans          查看用药计划列表
- POST   /api/medicine/record         老人确认已服/未服
- GET    /api/medicine/record         查看服药记录
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db, get_current_user
from schemas.common_schema import BaseResp, ok
from .service import (get_medicine_plan_list, create_medicine_plan, update_medicine_plan,
                      delete_medicine_plan, create_medicine_record, get_medicine_record_list)
from .schema import MedicinePlanSchema, MedicinePlanCreate, MedicinePlanUpdate, MedicineRecordCreate, MedicineRecordSchema

router = APIRouter(prefix="/api/medicine", tags=["用药"])


@router.get("/plans", response_model=BaseResp[list[MedicinePlanSchema]], summary="查看用药计划列表")
def get_plan_list(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 家属、老人本人都可以查看对应老人的用药计划
    if current_user.role not in ("family", "elder"):
        raise HTTPException(status_code=403, detail="仅家属或老人本人可查看用药计划")
    if not current_user.elder_id:
        raise HTTPException(status_code=400, detail="当前账号未绑定老人，无法查询用药计划")
    elder_id = current_user.elder_id
    data = get_medicine_plan_list(db, elder_id)
    return ok(data=data)


@router.post("/plans", response_model=BaseResp[MedicinePlanSchema], summary="家属新增用药计划")
def create_plan(
    plan_in: MedicinePlanCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 仅家属角色允许新增用药计划
    if current_user.role != "family":
        raise HTTPException(status_code=403, detail="仅家属角色可以新增用药计划")
    if not current_user.elder_id:
        raise HTTPException(status_code=400, detail="该家属账号还未绑定老人，无法新增用药计划")
    elder_id = current_user.elder_id
    data = create_medicine_plan(db, elder_id, plan_in)
    return ok(data=data)


@router.put("/plans/{plan_id}", response_model=BaseResp[MedicinePlanSchema], summary="家属编辑用药计划")
def update_plan(
    plan_id: int,
    plan_in: MedicinePlanUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if current_user.role != "family":
        raise HTTPException(status_code=403, detail="仅家属角色可以编辑用药计划")
    if not current_user.elder_id:
        raise HTTPException(status_code=400, detail="该家属账号还未绑定老人，无法编辑用药计划")
    elder_id = current_user.elder_id
    data = update_medicine_plan(db, plan_id, plan_in, elder_id)
    return ok(data=data)


@router.delete("/plans/{plan_id}", response_model=BaseResp, summary="家属删除用药计划")
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if current_user.role != "family":
        raise HTTPException(status_code=403, detail="仅家属角色可以删除用药计划")
    if not current_user.elder_id:
        raise HTTPException(status_code=400, detail="该家属账号还未绑定老人，无法删除用药计划")
    elder_id = current_user.elder_id
    delete_medicine_plan(db, plan_id, elder_id)
    return ok()


@router.post("/record", response_model=BaseResp[MedicineRecordSchema], summary="老人确认已服/未服")
def create_record(
    record_in: MedicineRecordCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 仅老人本人可以确认自己的服药情况
    if current_user.role != "elder":
        raise HTTPException(status_code=403, detail="仅老人本人可以确认服药")
    if not current_user.elder_id:
        raise HTTPException(status_code=400, detail="当前账号未绑定老人，无法确认服药")
    elder_id = current_user.elder_id
    data = create_medicine_record(db, record_in, elder_id)
    return ok(data=data)


@router.get("/record", response_model=BaseResp[list[MedicineRecordSchema]], summary="查看服药记录")
def get_record_list(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 家属、老人本人都可以查看对应老人的服药记录
    if current_user.role not in ("family", "elder"):
        raise HTTPException(status_code=403, detail="仅家属或老人本人可查看服药记录")
    if not current_user.elder_id:
        raise HTTPException(status_code=400, detail="当前账号未绑定老人，无法查询服药记录")
    elder_id = current_user.elder_id
    data = get_medicine_record_list(db, elder_id)
    return ok(data=data)
