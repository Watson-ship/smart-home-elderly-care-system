"""老人档案业务逻辑。
from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.elder import Elder
from domains.elder.schema import ElderCreateReq, ElderUpdateReq

def get_elder_list(db: Session, keyword: str = None, page: int = 1, size: int = 10):
    query = db.query(Elder)
    if keyword:
        query = query.filter(Elder.name.like(f"%{keyword}%"))
    total = query.count()
    items = query.offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": items}

def get_elder_by_id(db: Session, elder_id: int):
    elder = db.query(Elder).filter(Elder.id == elder_id).first()
    if not elder:
        raise HTTPException(status_code=404, detail="老人不存在")
    return elder

def create_elder(db: Session, data: ElderCreateReq):
    new_elder = Elder(**data.model_dump())
    db.add(new_elder)
    db.commit()
    db.refresh(new_elder)
    return new_elder

def update_elder(db: Session, elder_id: int, data: ElderUpdateReq):
    elder = get_elder_by_id(db, elder_id)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(elder, key, value)
    db.commit()
    db.refresh(elder)
    return elder
"""


# def create_elder(db, elder_create: ElderCreateReq):
#     ...
