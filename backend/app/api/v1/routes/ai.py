from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db

from app.ai.brain.decision_engine import DecisionEngine
from app.repositories.ai_memory_repository import AIMemoryRepository
from app.repositories.customer_timeline_repository import CustomerTimelineRepository
from app.models.ai_execution_queue import AIExecutionQueue
from app.models.ai_decision_log import AIDecisionLog

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)


@router.get("/health")
def ai_health():
    return {
        "status": "online",
        "brain": "active",
        "decision_engine": "active",
    }


@router.post("/think/{customer_id}")
def think(
    customer_id: int,
    db: Session = Depends(get_db),
):
    engine = DecisionEngine(db)
    return engine.evaluate(customer_id)


@router.get("/queue")
def queue(
    db: Session = Depends(get_db),
):
    return (
        db.query(AIExecutionQueue)
        .order_by(AIExecutionQueue.id.desc())
        .all()
    )


@router.get("/decision-logs")
def decision_logs(
    db: Session = Depends(get_db),
):
    return (
        db.query(AIDecisionLog)
        .order_by(AIDecisionLog.id.desc())
        .all()
    )


@router.get("/memory/{customer_id}")
def memory(
    customer_id: int,
    db: Session = Depends(get_db),
):
    repo = AIMemoryRepository(db)
    return repo.by_customer(customer_id)


@router.get("/timeline/{customer_id}")
def timeline(
    customer_id: int,
    db: Session = Depends(get_db),
):
    repo = CustomerTimelineRepository(db)
    return repo.by_customer(customer_id)

