from sqlalchemy.orm import Session

from app.ai.event_processor import AIEventProcessor


class AutomationRunner:

    def __init__(self, db: Session):
        self.db = db

    def run(self):

        print("========== AI Automation Cycle ==========")

        processor = AIEventProcessor(self.db)

        processor.process_pending()

        print("========== Cycle Complete ==========")
