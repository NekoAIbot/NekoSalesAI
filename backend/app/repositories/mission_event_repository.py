from sqlalchemy.orm import Session

from app.models.mission_event import MissionEvent


class MissionEventRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs):

        event = MissionEvent(**kwargs)

        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        return event

    def latest(self, limit: int = 100):

        return (
            self.db.query(MissionEvent)
            .order_by(
                MissionEvent.id.desc()
            )
            .limit(limit)
            .all()
        )

