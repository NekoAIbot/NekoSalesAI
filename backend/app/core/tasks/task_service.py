from app.database.database import SessionLocal
from app.models.ai_task import AITask


class TaskService:

    def create_task(
        self,
        customer_id,
        title,
        description="",
        priority="HIGH",
        assigned_to="Sales Team",
        task_type="FOLLOW_UP",
        organization_id=1,
    ):

        db = SessionLocal()

        try:

            task = AITask(
                organization_id=organization_id,
                customer_id=customer_id,
                task_type=task_type,
                title=title,
                description=description,
                priority=priority,
                status="pending",
                assigned_to=assigned_to,
            )

            db.add(task)
            db.commit()
            db.refresh(task)

            print("\n========== AI TASK ==========")
            print(f"Task ID    : {task.id}")
            print(f"Customer   : {customer_id}")
            print(f"Title      : {title}")
            print(f"Priority   : {priority}")
            print(f"Assigned   : {assigned_to}")
            print("=============================")

            return task

        finally:
            db.close()


task_service = TaskService()
