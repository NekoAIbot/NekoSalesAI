from datetime import datetime

from sqlalchemy.orm import Session

from app.models.ai_task import AITask
from app.models.ai_event import AIEvent
from app.models.priority_score import PriorityScore
from app.models.customer_timeline import CustomerTimeline


class CustomerAnalyzer:

    def __init__(self, db: Session):
        self.db = db

    def analyze_customer(self, customer_id: int):

        score = PriorityScore(
            customer_id=customer_id,
            score=50,
            reason="Initial AI evaluation",
        )

        event = AIEvent(
            customer_id=customer_id,
            event_type="customer_analyzed",
            description="Customer analyzed automatically.",
        )

        timeline = CustomerTimeline(
            customer_id=customer_id,
            event_type="AI_ANALYSIS",
            details="Initial customer analysis completed.",
        )

        task = AITask(
            customer_id=customer_id,
            task_type="FOLLOW_UP",
            title="Follow up with customer",
            description="AI recommends follow-up within 24 hours.",
            priority="MEDIUM",
            due_at=datetime.utcnow(),
        )

        self.db.add(score)
        self.db.add(event)
        self.db.add(timeline)
        self.db.add(task)

        self.db.commit()

        return {
            "status": "completed",
            "customer_id": customer_id,
        }

