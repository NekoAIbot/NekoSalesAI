from sqlalchemy.orm import Session

from app.models.lead import Lead


class LeadRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, lead: Lead):
        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def get(self, lead_id: int):
        return (
            self.db.query(Lead)
            .filter(Lead.id == lead_id)
            .first()
        )

    def get_all(self, status: str | None = None):
        query = self.db.query(Lead)

        if status:
            query = query.filter(Lead.status == status)

        return query.order_by(Lead.created_at.desc()).all()

    def update(self, lead: Lead):
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def delete(self, lead: Lead):
        self.db.delete(lead)
        self.db.commit()
