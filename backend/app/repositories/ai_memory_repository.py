from sqlalchemy.orm import Session

from app.models.ai_memory import AIMemory
from app.schemas.ai_memory import AIMemoryCreate


class AIMemoryRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: AIMemoryCreate):

        memory = AIMemory(**data.model_dump())

        self.db.add(memory)

        self.db.commit()

        self.db.refresh(memory)

        return memory

    def customer_memory(self, customer_id: int):

        return (
            self.db.query(AIMemory)
            .filter(AIMemory.customer_id == customer_id)
            .order_by(
                AIMemory.importance.desc(),
                AIMemory.created_at.desc(),
            )
            .all()
        )

    def organization_memory(self, organization_id: int):

        return (
            self.db.query(AIMemory)
            .filter(AIMemory.organization_id == organization_id)
            .order_by(
                AIMemory.importance.desc(),
                AIMemory.created_at.desc(),
            )
            .all()
        )
