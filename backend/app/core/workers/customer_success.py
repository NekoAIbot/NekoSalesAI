from datetime import datetime

from app.models.customer import Customer


class CustomerSuccessWorker:

    def __init__(self, db):
        self.db = db


    def run(self, payload):

        customer_id = payload.get("customer_id")

        print("\n========== CUSTOMER SUCCESS ==========")

        customer = self.db.get(
            Customer,
            customer_id
        )

        if not customer:
            print("Customer not found:", customer_id)
            return False


        action = payload.get(
            "action",
            "FOLLOW_UP"
        )

        reason = payload.get(
            "reason",
            "Customer activity"
        )


        print("Customer :", customer.id)
        print("Action   :", action)
        print("Reason   :", reason)


        # Existing customer success logic remains here.
        # Future:
        # - send message
        # - create task
        # - assign owner
        # - escalation


        print(
            "Customer Success executed."
        )

        print("======================================")


        return {
            "customer_id": customer.id,
            "executed": True,
            "action": action,
            "timestamp": datetime.utcnow().isoformat()
        }
