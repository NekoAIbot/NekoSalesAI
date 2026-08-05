from sqlalchemy.orm import Session

from app.ai.decision_engine import AIDecisionEngine
from app.schemas.ai_memory import AIMemoryCreate
from app.services.ai_event_service import AIEventService
from app.services.ai_memory_service import AIMemoryService
from app.services.timeline_service import TimelineService


class AIEventProcessor:

    def __init__(self, db: Session):

        self.db = db

        self.events = AIEventService(db)
        self.memory = AIMemoryService(db)
        self.timeline = TimelineService(db)

        self.decision_engine = AIDecisionEngine()

    def process_pending(self):

        events = self.events.pending()

        for event in events:
            self.process(event)

    def process(self, event):

        decision = self.decision_engine.evaluate(event)

        print(
            f"[AI] {decision.action} | "
            f"{decision.confidence:.2f} | "
            f"{decision.reason}"
        )

        self.memory.remember(
            AIMemoryCreate(
                organization_id=event.organization_id,
                customer_id=event.customer_id,
                memory_type=event.event_type,
                importance=5,
                content=event.payload,
            )
        )

        if decision.notify_owner:
            print("[AI] Manager notification queued.")

        event.status = "processed"

        self.db.commit()
