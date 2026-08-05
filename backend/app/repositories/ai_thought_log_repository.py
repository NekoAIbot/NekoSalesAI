from sqlalchemy.orm import Session

from app.models.ai_thought_log import AIThoughtLog


class AIThoughtLogRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs):

        thought = AIThoughtLog(**kwargs)

        self.db.add(thought)
        self.db.commit()
        self.db.refresh(thought)

        return thought

    def by_customer(self, customer_id: int):

        return (
            self.db.query(AIThoughtLog)
            .filter(
                AIThoughtLog.customer_id == customer_id
            )
            .order_by(
                AIThoughtLog.id.desc()
            )
            .all()
        )

