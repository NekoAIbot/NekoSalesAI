from app.core.events.customer_events import queue_customer_review


def customer_profile_updated(customer_id: int):
    queue_customer_review(
        customer_id=customer_id,
        reason="Profile updated",
    )


def note_added(customer_id: int):
    queue_customer_review(
        customer_id=customer_id,
        reason="Note added",
    )


def meeting_completed(customer_id: int):
    queue_customer_review(
        customer_id=customer_id,
        reason="Meeting completed",
    )


def phone_call_logged(customer_id: int):
    queue_customer_review(
        customer_id=customer_id,
        reason="Phone call",
    )


def opportunity_created(customer_id: int):
    queue_customer_review(
        customer_id=customer_id,
        reason="Opportunity created",
    )


def opportunity_value_increased(customer_id: int):
    queue_customer_review(
        customer_id=customer_id,
        reason="Opportunity value increased",
    )
