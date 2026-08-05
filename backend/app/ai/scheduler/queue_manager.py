from app.repositories.ai_execution_queue_repository import (
    AIExecutionQueueRepository,
)


class QueueManager:

    def __init__(self, db):

        self.repository = AIExecutionQueueRepository(db)

    def enqueue(
        self,
        customer_id: int,
        reason: str,
    ):

        return self.repository.create(
            customer_id=customer_id,
            task_type="AI_THINK",
            payload=reason,
        )

    def next(self):

        return self.repository.next_pending()

    def complete(
        self,
        task_id: int,
    ):

        task = self.repository.get(task_id)

        if task:
            self.repository.mark_completed(task)

