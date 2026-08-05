from datetime import datetime

from app.database.database import SessionLocal
from app.core.brain.brain_logger import BrainLogger


class BrainActivityStream:

    def __init__(self):
        self.listeners = []

    def subscribe(self, listener):
        self.listeners.append(listener)

    def publish(
        self,
        stage: str,
        message: str,
        customer_id=None,
        worker=None,
        confidence=None,
    ):

        event = {
            "time": datetime.utcnow().isoformat(),
            "stage": stage,
            "worker": worker,
            "customer_id": customer_id,
            "message": message,
            "confidence": confidence,
        }

        db = SessionLocal()

        try:
            BrainLogger(db).save(
                stage=stage,
                customer_id=customer_id,
                message=message,
                confidence=confidence,
            )
        finally:
            db.close()

        print("\n========== AI BRAIN ==========")
        print(event)
        print("==============================\n")

        for listener in self.listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[BRAIN ERROR] {e}")


brain = BrainActivityStream()

