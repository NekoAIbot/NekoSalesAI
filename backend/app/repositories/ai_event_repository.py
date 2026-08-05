from sqlalchemy.orm import Session

from app.models.ai_event import AIEvent


class AIEventRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs):

        event = AIEvent(**kwargs)

        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        return event

    def latest(self, limit: int = 100):

        return (
            self.db.query(AIEvent)
            .order_by(AIEvent.id.desc())
            .limit(limit)
            .all()
        )

    def by_customer(self, customer_id: int):

        return (
            self.db.query(AIEvent)
            .filter(AIEvent.customer_id == customer_id)
            .order_by(AIEvent.id.desc())
            .all()
        )

