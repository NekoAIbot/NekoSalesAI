from sqlalchemy.orm import Session

from app.models.ai_thought_log import AIThoughtLog


class BrainLogger:

    def __init__(self, db: Session):
        self.db = db

    def save(
        self,
        stage: str,
        customer_id: int | None,
        message: str,
        confidence: float | None = None,
    ):

        thought = AIThoughtLog(
            customer_id=customer_id,
            stage=stage,
            message=message,
            confidence=confidence,
        )

        self.db.add(thought)
        self.db.commit()

