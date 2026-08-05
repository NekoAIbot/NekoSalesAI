from datetime import datetime, timedelta

from app.models.customer import Customer
from app.core.workers.dispatcher import dispatcher


class CustomerReviewWorker:

    def __init__(self, db):
        self.db = db

    def run(self, payload):

        customer = self.db.get(
            Customer,
            payload["customer_id"],
        )

        if not customer:
            print("Customer not found.")
            return False

        trigger = payload.get(
            "trigger",
            "Scheduled Review",
        )

        priority = payload.get(
            "priority",
            "MEDIUM",
        )

        reasons = payload.get("reasons")

        if not reasons:
            reasons = [
                payload.get(
                    "reason",
                    "Scheduled review",
                )
            ]

        print("\n========== CUSTOMER REVIEW ==========")
        print("Customer :", customer.id)
        print("Trigger  :", trigger)
        print("Priority :", priority)

        print("\nReasons:")
        for reason in reasons:
            print(f" - {reason}")

        print("====================================")

        # Existing AI logic stays here

        customer.last_reviewed_at = datetime.utcnow()
        customer.next_review_at = (
            datetime.utcnow()
            + timedelta(hours=24)
        )

        self.db.commit()

        dispatcher.assign(
            "customer_success",
            {
                "customer_id": customer.id,
                "action": "FOLLOW_UP",
                "reason": reasons[0],
                "priority": priority,
            },
            priority=priority,
        )

        print("Next review:", customer.next_review_at)

        return True
