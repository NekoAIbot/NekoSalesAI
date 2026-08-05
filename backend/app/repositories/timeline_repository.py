from sqlalchemy.orm import Session

from app.models.timeline_event import TimelineEvent
from app.schemas.timeline import TimelineCreate


class TimelineRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: TimelineCreate):

        event = TimelineEvent(**data.model_dump())

        self.db.add(event)

        self.db.commit()

        self.db.refresh(event)

        return event

    def list_by_customer(self, customer_id: int):

        return (
            self.db.query(TimelineEvent)
            .filter(TimelineEvent.customer_id == customer_id)
            .order_by(TimelineEvent.created_at.desc())
            .all()
        )

    def list_by_org(self, organization_id: int):

        return (
            self.db.query(TimelineEvent)
            .filter(TimelineEvent.organization_id == organization_id)
            .order_by(TimelineEvent.created_at.desc())
            .all()
        )
