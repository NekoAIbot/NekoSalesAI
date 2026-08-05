
from app.core.workers.worker_registry import worker_registry
from app.core.workers.sales_task_worker import sales_task_worker

from datetime import datetime
from itertools import count
from queue import PriorityQueue


PRIORITY_ORDER = {
    "HIGH": 0,
    "MEDIUM": 1,
    "LOW": 2,
}


class WorkerDispatcher:

    def __init__(self):
        self.queue = PriorityQueue()

        # FIFO counter for jobs with same priority
        self.sequence = count()

        # customer_id -> queued customer_review job
        self.pending_reviews = {}

    def assign(
        self,
        worker: str,
        payload: dict,
        priority: str = "MEDIUM",
    ):

        priority = priority.upper()

        if priority not in PRIORITY_ORDER:
            priority = "MEDIUM"

        #
        # Merge duplicate customer reviews
        #
        if worker == "customer_review":

            customer_id = payload["customer_id"]

            existing = self.pending_reviews.get(customer_id)

            if existing:

                #
                # Merge reasons
                #
                reasons = existing["payload"].setdefault("reasons", [])

                incoming_reason = payload.get("reason")

                if incoming_reason and incoming_reason not in reasons:
                    reasons.append(incoming_reason)

                #
                # Upgrade priority
                #
                if (
                    PRIORITY_ORDER[priority]
                    < PRIORITY_ORDER[existing["priority"]]
                ):
                    existing["priority"] = priority

                print(
                    f"[MERGED] customer_review "
                    f"Customer={customer_id} "
                    f"Priority={existing['priority']}"
                )

                return

        job = {
            "worker": worker,
            "payload": payload,
            "priority": priority,
            "created_at": datetime.utcnow(),
        }

        self.queue.put(
            (
                PRIORITY_ORDER[priority],
                next(self.sequence),
                job,
            )
        )

        if worker == "customer_review":
            self.pending_reviews[payload["customer_id"]] = job

        print(
            f"[DISPATCH] {worker} "
            f"Priority={priority}"
        )

    def next_job(self):

        if self.queue.empty():
            return None

        _, _, job = self.queue.get()

        if job["worker"] == "customer_review":

            customer_id = job["payload"]["customer_id"]

            self.pending_reviews.pop(
                customer_id,
                None,
            )

        result = worker_registry.execute(
            job["worker"],
            job["payload"]
        )

        print(f"[WORKER RESULT] {result}")

        return job

    def has_customer_review(
        self,
        customer_id: int,
    ):

        return customer_id in self.pending_reviews


dispatcher = WorkerDispatcher()


worker_registry.register(
    "CREATE_SALES_TASK",
    sales_task_worker.run
)
