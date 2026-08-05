from datetime import datetime

from sqlalchemy import or_

from app.models.customer import Customer
from app.core.events.customer_events import queue_customer_review


class CustomerScanner:

    def __init__(self, db):
        self.db = db

    def scan(self):

        print("\n========== CUSTOMER SCANNER ==========")

        now = datetime.utcnow()

        customers = (
            self.db.query(Customer)
            .filter(
                Customer.is_active == True,
                or_(
                    Customer.next_review_at == None,
                    Customer.next_review_at <= now,
                ),
            )
            .all()
        )

        if not customers:
            print("No customers due for review.")

            skipped = (
                self.db.query(Customer)
                .filter(Customer.is_active == True)
                .all()
            )

            for customer in skipped:

                if customer.next_review_at:

                    print(
                        f"Skipping customer review: {customer.id}"
                    )

                    print(
                        f"Next review: {customer.next_review_at}"
                    )

            print("======================================")
            return

        for customer in customers:

            queue_customer_review(
                customer_id=customer.id,
                reason="Scheduled Review",
                trigger="Scheduled Review",
            )

            print(
                f"Queued customer review: {customer.id}"
            )

            print("Reason: Scheduled Review")

        print("======================================")
