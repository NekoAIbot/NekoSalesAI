from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadUpdate


def create_lead(db: Session, lead: LeadCreate):
    obj = Lead(**lead.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_lead(db: Session, lead_id: int):
    return db.query(Lead).filter(Lead.id == lead_id).first()


def get_leads(db: Session):
    return db.query(Lead).all()


def update_lead(db: Session, lead_id: int, data: LeadUpdate):
    obj = get_lead(db, lead_id)

    if not obj:
        return None

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)

    db.commit()
    db.refresh(obj)
    return obj


def delete_lead(db: Session, lead_id: int):
    obj = get_lead(db, lead_id)

    if not obj:
        return False

    db.delete(obj)
    db.commit()
    return True
