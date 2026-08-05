from sqlalchemy.orm import Session

from app.repositories.timeline_repository import TimelineRepository
from app.schemas.timeline import TimelineCreate


class TimelineService:

    def __init__(self, db: Session):
        self.repository = TimelineRepository(db)

    def create(self, data: TimelineCreate):
        return self.repository.create(data)

    def customer_history(self, customer_id: int):
        return self.repository.list_by_customer(customer_id)

    def organization_history(self, organization_id: int):
        return self.repository.list_by_org(organization_id)
