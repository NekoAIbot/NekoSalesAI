from app.core.events import event_bus
from app.core.events.events import (
    CUSTOMER_ACTION_REQUIRED,
    CUSTOMER_CREATED,
    DECISION_CREATED,
    MESSAGE_RECEIVED,
    PAYMENT_RECEIVED,
)
from app.core.workers.dispatcher import dispatcher


def handle_decision(payload):

    action = payload.get("action")

    if action == "START_CONVERSATION":

        dispatcher.assign(
            "conversation_agent",
            payload,
        )

    else:

        dispatcher.assign(
            "execution_agent",
            payload,
        )


def register_workers():

    event_bus.subscribe(
        CUSTOMER_CREATED,
        lambda payload: dispatcher.assign(
            "customer_onboarding",
            payload,
        ),
    )


    event_bus.subscribe(
        MESSAGE_RECEIVED,
        lambda payload: dispatcher.assign(
            "conversation_agent",
            payload,
        ),
    )


    event_bus.subscribe(
        DECISION_CREATED,
        handle_decision,
    )


    event_bus.subscribe(
        CUSTOMER_ACTION_REQUIRED,
        lambda payload: dispatcher.assign(
            "customer_success",
            payload,
        ),
    )


    event_bus.subscribe(
        PAYMENT_RECEIVED,
        lambda payload: dispatcher.assign(
            "customer_success",
            payload,
        ),
    )
