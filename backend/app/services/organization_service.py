from sqlalchemy.orm import Session

from app.repositories.organization_repository import OrganizationRepository
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
)


class OrganizationService:

    def __init__(self, db: Session):
        self.repository = OrganizationRepository(db)

    def create(self, organization: OrganizationCreate):
        return self.repository.create(organization)

    def get(self, organization_id: int):
        return self.repository.get_by_id(organization_id)

    def list(self):
        return self.repository.get_all()

    def update(self, organization_id: int, data: OrganizationUpdate):
        org = self.repository.get_by_id(organization_id)

        if org is None:
            return None

        return self.repository.update(org, data)

    def delete(self, organization_id: int):
        org = self.repository.get_by_id(organization_id)

        if org is None:
            return False

        self.repository.delete(org)
        return True
