from sqlalchemy.orm import Session

from app.repositories.ai_memory_repository import AIMemoryRepository
from app.schemas.ai_memory import AIMemoryCreate


class AIMemoryService:

    def __init__(self, db: Session):
        self.repository = AIMemoryRepository(db)

    def remember(self, data: AIMemoryCreate):
        return self.repository.create(data)

    def customer_memory(self, customer_id: int):
        return self.repository.customer_memory(customer_id)

    def organization_memory(self, organization_id: int):
        return self.repository.organization_memory(organization_id)
