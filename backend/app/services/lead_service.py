from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.repositories.lead_repository import LeadRepository
from app.schemas.lead import LeadCreate, LeadUpdate


class LeadService:

    def __init__(self, db: Session):
        self.repository = LeadRepository(db)

    def create(self, organization_id: int, data: LeadCreate):
        dump = data.model_dump()
        dump["organization_id"] = organization_id
        lead = Lead(**dump)
        return self.repository.create(lead)

    def list(self, organization_id: int, status: str | None = None):
        return self.repository.get_all(organization_id, status=status)

    def get(self, organization_id: int, lead_id: int):
        return self.repository.get(organization_id, lead_id)

    def update(self, organization_id: int, lead_id: int, data: LeadUpdate):
        lead = self.repository.get(organization_id, lead_id)

        if lead is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            if key != "organization_id":
                setattr(lead, key, value)

        return self.repository.update(lead)

    def delete(self, organization_id: int, lead_id: int):
        lead = self.repository.get(organization_id, lead_id)

        if lead is None:
            return False

        self.repository.delete(lead)
        return True
