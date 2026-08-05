from app.core.events import event_bus
from app.core.events.events import CUSTOMER_CREATED


def logger(payload):
    print("EVENT RECEIVED")
    print(payload)


event_bus.subscribe(
    CUSTOMER_CREATED,
    logger,
)

event_bus.publish(
    CUSTOMER_CREATED,
    {
        "customer_id": 1,
        "name": "John Doe",
    },
)

