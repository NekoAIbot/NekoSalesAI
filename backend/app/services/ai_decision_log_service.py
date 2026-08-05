from sqlalchemy.orm import Session

from app.repositories.ai_decision_log_repository import (
    AIDecisionLogRepository,
)


class AIDecisionLogService:

    def __init__(self, db: Session):
        self.repository = AIDecisionLogRepository(db)

    def log(self, decision):

        return self.repository.create(

            customer_id=decision["customer_id"],

            action=decision["action"],

            priority=decision["priority"],

            reason=decision["reason"],

            decision_data=str(decision),

            executed="PENDING",
        )

