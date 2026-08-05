from fastapi import APIRouter
from app.database.database import SessionLocal
from app.models.ai_task import AITask

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
)


@router.get("/")
def list_tasks():

    db = SessionLocal()

    try:

        tasks = (
            db.query(AITask)
            .order_by(AITask.created_at.desc())
            .all()
        )

        return [
            {
                "id": task.id,
                "customer_id": task.customer_id,
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "status": task.status,
                "assigned_to": task.assigned_to,
                "due_at": (
                    task.due_at.isoformat()
                    if task.due_at
                    else None
                ),
                "created_at": (
                    task.created_at.isoformat()
                    if task.created_at
                    else None
                ),
            }
            for task in tasks
        ]

    finally:
        db.close()


@router.get("/{task_id}")
def get_task(task_id: int):

    db = SessionLocal()

    try:

        task = (
            db.query(AITask)
            .filter(AITask.id == task_id)
            .first()
        )

        if task is None:
            return {
                "success": False,
                "message": "Task not found",
            }

        return {
            "success": True,
            "task": {
                "id": task.id,
                "customer_id": task.customer_id,
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "status": task.status,
                "assigned_to": task.assigned_to,
                "due_at": (
                    task.due_at.isoformat()
                    if task.due_at
                    else None
                ),
                "created_at": (
                    task.created_at.isoformat()
                    if task.created_at
                    else None
                ),
            },
        }

    finally:
        db.close()
