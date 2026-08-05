from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
)


class OrganizationRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, organization: OrganizationCreate) -> Organization:
        db_org = Organization(**organization.model_dump())

        self.db.add(db_org)
        self.db.commit()
        self.db.refresh(db_org)

        return db_org

    def get_by_id(self, organization_id: int) -> Organization | None:
        return (
            self.db.query(Organization)
            .filter(Organization.id == organization_id)
            .first()
        )

    def get_by_slug(self, slug: str) -> Organization | None:
        return (
            self.db.query(Organization)
            .filter(Organization.slug == slug)
            .first()
        )

    def get_all(self) -> list[Organization]:
        return (
            self.db.query(Organization)
            .order_by(Organization.name)
            .all()
        )

    def update(
        self,
        db_org: Organization,
        organization: OrganizationUpdate,
    ) -> Organization:

        update_data = organization.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            setattr(db_org, key, value)

        self.db.commit()
        self.db.refresh(db_org)

        return db_org

    def delete(self, db_org: Organization) -> None:
        self.db.delete(db_org)
        self.db.commit()
