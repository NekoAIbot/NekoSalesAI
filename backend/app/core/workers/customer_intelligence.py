from datetime import datetime

from app.models.ai_memory import AIMemory
from app.models.customer import Customer


class CustomerIntelligenceWorker:

    def __init__(self, db):
        self.db = db

    def run(self, payload):

        customer = self.db.get(
            Customer,
            payload["customer_id"],
        )

        if customer is None:
            print("Customer not found.")
            return False

        print("\n========== CUSTOMER INTELLIGENCE ==========")
        print("Customer :", customer.id)
        print("Trigger  :", payload.get("trigger"))
        print("Reason   :", payload.get("reason"))

        memory = (
            self.db.query(AIMemory)
            .filter(AIMemory.customer_id == customer.id)
            .first()
        )

        if memory is None:

            memory = AIMemory(
                customer_id=customer.id,
                memory_type="LIVE_INTELLIGENCE",
                content="Customer intelligence profile created.",
            )

            self.db.add(memory)

            print("Created live intelligence profile.")

        else:

            existing = memory.content or ""

            update = (
                f"\n[{datetime.utcnow()}] "
                f"{payload.get('reason')}"
            )

            memory.content = existing + update

            print("Updated live intelligence profile.")

        self.db.commit()

        return {
            "customer_id": customer.id,
            "intelligence_updated": True,
        }
