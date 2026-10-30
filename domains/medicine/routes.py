"""用药接口。
- POST   /api/medicine/plan          家属新增用药计划
- PUT    /api/medicine/plan/{id}     家属编辑用药计划
- DELETE /api/medicine/plan/{id}     家属删除用药计划
- GET    /api/medicine/plan          查看用药计划列表
- POST   /api/medicine/record        老人确认已服/未服
- GET    /api/medicine/record        查看服药记录
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db, get_current_user
from schemas.common_schema import BaseResp, ok
from .service import get_medicine_plan_list, create_medicine_plan
from .schema import MedicinePlanSchema, MedicinePlanCreate

router = APIRouter(prefix="/api/medicine", tags=["用药"])


@router.get("/plan", response_model=BaseResp[list[MedicinePlanSchema]], summary="查看用药计划列表")
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


@router.post("/plan", response_model=BaseResp[MedicinePlanSchema], summary="家属新增用药计划")
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
