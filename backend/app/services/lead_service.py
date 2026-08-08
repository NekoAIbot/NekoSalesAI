from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.repositories.lead_repository import LeadRepository
from app.schemas.lead import LeadCreate, LeadUpdate


class LeadService:

    def __init__(self, db: Session):
        self.repository = LeadRepository(db)

    def create(self, data: LeadCreate):
        lead = Lead(**data.model_dump())
        return self.repository.create(lead)

    def list(self, status: str | None = None):
        return self.repository.get_all(status=status)

    def get(self, lead_id: int):
        return self.repository.get(lead_id)

    def update(self, lead_id: int, data: LeadUpdate):
        lead = self.repository.get(lead_id)

        if lead is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(lead, key, value)

        return self.repository.update(lead)

    def delete(self, lead_id: int):
        lead = self.repository.get(lead_id)

        if lead is None:
            return False

        self.repository.delete(lead)
        return True
