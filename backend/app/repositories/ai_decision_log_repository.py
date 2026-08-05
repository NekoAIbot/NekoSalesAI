from sqlalchemy.orm import Session

from app.models.ai_decision_log import AIDecisionLog


class AIDecisionLogRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs):

        log = AIDecisionLog(**kwargs)

        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)

        return log

    def latest(self, limit: int = 100):

        return (
            self.db.query(AIDecisionLog)
            .order_by(AIDecisionLog.created_at.desc())
            .limit(limit)
            .all()
        )

    def customer_history(self, customer_id: int):

        return (
            self.db.query(AIDecisionLog)
            .filter(
                AIDecisionLog.customer_id == customer_id
            )
            .order_by(AIDecisionLog.created_at.desc())
            .all()
        )

