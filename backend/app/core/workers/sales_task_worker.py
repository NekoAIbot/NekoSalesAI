from app.core.workers.base_worker import BaseWorker
from app.core.tasks.task_service import task_service
from app.core.activity.activity_logger import activity_logger
from app.core.timeline.timeline_service import timeline_service


class SalesTaskWorker(BaseWorker):

    worker_name = "CREATE_SALES_TASK"

    def execute(self, payload):

        customer_id = payload["customer_id"]

        message = payload.get(
            "message",
            "AI detected a follow-up opportunity."
        )

        priority = payload.get(
            "priority",
            "HIGH",
        )

        task = task_service.create_task(
            customer_id=customer_id,
            title="AI Sales Follow-up",
            description=message,
            priority=priority,
            assigned_to="Sales Team",
        )

        activity_logger.log(
            event_type="SALES_TASK_CREATED",
            title="AI created a sales task",
            description=message,
            customer_id=customer_id,
            priority=priority,
        )

        timeline_service.add_event(
            customer_id=customer_id,
            event_type="SALES_TASK_CREATED",
            title="AI created a sales follow-up",
            description=message,
            metadata={
                "task_id": task.id,
                "priority": priority,
                "worker": self.worker_name,
            },
        )

        print("\n========== SALES TASK WORKER ==========")
        print(f"Customer : {customer_id}")
        print(f"Task ID  : {task.id}")
        print(f"Priority : {priority}")
        print("======================================")

        return {
            "task_created": True,
            "task_id": task.id,
            "priority": priority,
            "assigned_to": "Sales Team",
        }


sales_task_worker = SalesTaskWorker()
