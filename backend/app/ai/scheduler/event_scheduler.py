from app.ai.scheduler.queue_manager import QueueManager
from app.ai.scheduler.worker import SchedulerWorker


class EventScheduler:

    def __init__(
        self,
        db,
    ):

        self.queue = QueueManager(db)
        self.worker = SchedulerWorker(db)

    def run(self):

        task = self.queue.next()

        if task is None:
            return

        self.worker.process_customer(
            task.customer_id,
        )

        self.queue.complete(task.id)

