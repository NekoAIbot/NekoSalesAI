from app.database.database import SessionLocal
from app.models.activity_event import ActivityEvent


class ActivityLogger:

    def log(
        self,
        event_type,
        title,
        description="",
        customer_id=None,
        source="AI",
        priority="MEDIUM",
    ):
        db = SessionLocal()

        try:
            event = ActivityEvent(
                customer_id=customer_id,
                event_type=event_type,
                title=title,
                description=description,
                source=source,
                priority=priority,
            )

            db.add(event)
            db.commit()
            db.refresh(event)

            print("\n========== ACTIVITY LOGGER ==========")
            print(f"Event ID : {event.id}")
            print(f"Type     : {event_type}")
            print(f"Title    : {title}")
            print("====================================")

            return event.id

        finally:
            db.close()


activity_logger = ActivityLogger()
