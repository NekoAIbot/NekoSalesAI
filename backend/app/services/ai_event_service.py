from sqlalchemy.orm import Session

from app.repositories.ai_event_repository import AIEventRepository
from app.schemas.ai_event import AIEventCreate


class AIEventService:

    def __init__(self, db: Session):
        self.repository = AIEventRepository(db)

    def publish(self, event: AIEventCreate):
        return self.repository.create(event)

    def pending(self):
        return self.repository.pending()
