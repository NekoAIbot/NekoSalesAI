from app.services.ai_execution_queue_service import (
    AIExecutionQueueService,
)


class ExecutionWorker:

    def __init__(self, db):
        self.queue = AIExecutionQueueService(db)

    def process_next(self):

        job = self.queue.next_job()

        if job is None:
            return False

        print()

        print("========== AI WORKER ==========")
        print("Action :", job.action)
        print("Payload:", job.payload)
        print("===============================")

        job.status = "COMPLETED"

        self.queue.save()

        return True

