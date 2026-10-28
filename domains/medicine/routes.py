"""用药接口。
- POST   /api/medicine/plan          家属新增用药计划
- PUT    /api/medicine/plan/{id}     家属编辑用药计划
- DELETE /api/medicine/plan/{id}     家属删除用药计划
- GET    /api/medicine/plan          查看用药计划列表
- POST   /api/medicine/record        老人确认已服/未服
- GET    /api/medicine/record        查看服药记录
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.session import get_db, get_current_user
from schemas.common_schema import BaseResp
from .service import get_medicine_plan_list
from .schema import MedicinePlanSchema

router = APIRouter(prefix="/api/medicine", tags=["用药"])

@router.get("/plan", response_model=BaseResp[list[MedicinePlanSchema]])
def get_plan_list(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    elder_id = current_user["elder_id"]
    data = get_medicine_plan_list(db, elder_id)
    return BaseResp.success(data=data)
