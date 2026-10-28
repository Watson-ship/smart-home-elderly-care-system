from sqlalchemy.orm import Session
from models.medicine_plan import MedicinePlan
from domains.medicine.schema import MedicinePlanSchema

def get_medicine_plan_list(db: Session, elder_id: int):
    """按elder_id查询用药计划，权限隔离"""
    plan_list = db.query(MedicinePlan).filter(MedicinePlan.elder_id == elder_id).all()
    return [MedicinePlanSchema.model_validate(item) for item in plan_list]
