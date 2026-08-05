from app.database.database import SessionLocal
from app.models.customer import Customer
from app.core.workers.dispatcher import dispatcher


EVENT_PRIORITIES = {
    "Opportunity created": "HIGH",
    "Opportunity value increased": "HIGH",
    "Deal moved to Proposal": "HIGH",
    "Deal moved to Negotiation": "HIGH",
    "Pricing requested": "HIGH",
    "Demo requested": "HIGH",

    "WhatsApp received": "MEDIUM",
    "Email received": "MEDIUM",
    "Live chat": "MEDIUM",
    "Meeting completed": "MEDIUM",
    "Phone call": "MEDIUM",

    "Note added": "LOW",
    "Profile updated": "LOW",
    "Internal comment": "LOW",
    "Tag changed": "LOW",

    "Scheduled Review": "MEDIUM",
}


def queue_customer_review(
    customer_id: int,
    reason: str,
    trigger: str = "Event Review",
):

    db = SessionLocal()

    try:

        customer = db.get(Customer, customer_id)

        if customer is None:
            return

        priority = EVENT_PRIORITIES.get(reason, "MEDIUM")

        #
        # IMPORTANT:
        #
        # Event reviews ALWAYS bypass the cooldown.
        #
        # Only the scheduler checks next_review_at.
        #

        dispatcher.assign(
            worker="customer_review",
            payload={
                "customer_id": customer_id,
                "trigger": trigger,
                "reason": reason,
                "reasons": [reason],
                "priority": priority,
            },
            priority=priority,
        )

    finally:
        db.close()
