from datetime import datetime

from sqlalchemy.orm import Session

from app.models.mission_event import MissionEvent


class MissionControl:

    def __init__(self, db: Session):
        self.db = db

    def publish(
        self,
        source: str,
        level: str,
        title: str,
        message: str,
    ):

        event = MissionEvent(
            source=source,
            level=level,
            title=title,
            message=message,
            created_at=datetime.utcnow(),
        )

        self.db.add(event)
        self.db.commit()

        print()

        print("========== MISSION CONTROL ==========")
        print(level)
        print(title)
        print(message)
        print("====================================")

        print()


