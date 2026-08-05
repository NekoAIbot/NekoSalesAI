from datetime import datetime

from sqlalchemy.orm import Session

from app.models.ai_task import AITask
from app.models.ai_memory import AIMemory
from app.models.priority_score import PriorityScore
from app.models.customer_timeline import CustomerTimeline


class AIObserver:

    def __init__(self, db: Session):
        self.db = db

    def observe_customer(self, customer_id: int):

        timeline = (
            self.db.query(CustomerTimeline)
            .filter(
                CustomerTimeline.customer_id == customer_id
            )
            .order_by(CustomerTimeline.created_at.desc())
            .all()
        )

        memories = (
            self.db.query(AIMemory)
            .filter(
                AIMemory.customer_id == customer_id
            )
            .all()
        )

        tasks = (
            self.db.query(AITask)
            .filter(
                AITask.customer_id == customer_id
            )
            .all()
        )

        score = (
            self.db.query(PriorityScore)
            .filter(
                PriorityScore.customer_id == customer_id
            )
            .first()
        )

        return {
            "customer_id": customer_id,
            "timeline": timeline,
            "memories": memories,
            "tasks": tasks,
            "priority": score,
            "last_scan": datetime.utcnow(),
        }
