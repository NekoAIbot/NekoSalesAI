from app.database.database import SessionLocal
from app.models.customer_timeline import CustomerTimeline


class TimelineService:

    def add_event(
        self,
        customer_id,
        event_type,
        title,
        description="",
        metadata=None,
    ):
        db = SessionLocal()

        try:
            row = CustomerTimeline(
                customer_id=customer_id,
                event_type=event_type,
                title=title,
                description=description,
                event_metadata=metadata or {},
            )

            db.add(row)
            db.commit()
            db.refresh(row)

            print("\n========== TIMELINE ==========")
            print(f"Customer : {customer_id}")
            print(f"Event    : {event_type}")
            print(f"Title    : {title}")
            print("==============================")

            return row.id

        finally:
            db.close()


timeline_service = TimelineService()
