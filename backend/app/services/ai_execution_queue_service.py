from app.repositories.ai_execution_queue_repository import (
    AIExecutionQueueRepository,
)


class AIExecutionQueueService:

    def __init__(self, db):
        self.repository = AIExecutionQueueRepository(db)

    def enqueue(self, action, payload):

        return self.repository.create(
            action=action,
            payload=str(payload),
            status="PENDING",
        )

    def next_job(self):
        return self.repository.next_job()

    def save(self):
        self.repository.save()

