from datetime import datetime

from app.core.events import event_bus
from app.core.events.events import DECISION_CREATED


class CustomerOnboardingWorker:

    def __init__(self, db):
        self.db = db


    def run(self, payload):

        print("\n========== CUSTOMER ONBOARDING ==========")


        if isinstance(payload, dict):
            customer_id = payload.get("customer_id")
        else:
            customer_id = payload


        print(f"Loading customer {customer_id}")


        thought = (
            "New customer detected. "
            "Starting onboarding workflow."
        )


        print("AI Thought:")
        print(thought)


        decision = {
            "customer_id": customer_id,
            "action": "START_CONVERSATION",
            "reason": "New lead requires introduction.",
            "created_at": datetime.utcnow().isoformat(),
        }


        print("Decision:")
        print(decision)


        event_bus.publish(
            DECISION_CREATED,
            decision,
        )


        print("=========================================\n")
