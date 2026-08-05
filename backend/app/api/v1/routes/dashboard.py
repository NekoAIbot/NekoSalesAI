from fastapi import APIRouter

from app.database.database import SessionLocal
from app.models.ai_task import AITask
from app.models.activity_event import ActivityEvent
from app.models.customer_timeline import CustomerTimeline

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


@router.get("/summary")
def dashboard_summary():

    db = SessionLocal()

    try:

        total_tasks = db.query(AITask).count()

        open_tasks = (
            db.query(AITask)
            .filter(AITask.status == "pending")
            .count()
        )

        completed_tasks = (
            db.query(AITask)
            .filter(AITask.status == "completed")
            .count()
        )

        activity_events = db.query(ActivityEvent).count()

        timeline_events = db.query(CustomerTimeline).count()

        return {
            "tasks": {
                "total": total_tasks,
                "open": open_tasks,
                "completed": completed_tasks,
            },
            "activity_events": activity_events,
            "timeline_events": timeline_events,
        }

    finally:
        db.close()
