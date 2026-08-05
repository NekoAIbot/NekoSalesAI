from sqlalchemy.orm import Session

from app.models.ai_execution_queue import AIExecutionQueue


class AIExecutionQueueRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs):

        job = AIExecutionQueue(**kwargs)

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        return job

    def next_job(self):

        return (
            self.db.query(AIExecutionQueue)
            .filter(
                AIExecutionQueue.status == "PENDING"
            )
            .order_by(AIExecutionQueue.id.asc())
            .first()
        )

    def save(self):

        self.db.commit()

