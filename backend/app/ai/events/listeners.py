from app.ai.events.event_bus import event_bus
from app.ai.events import events


def customer_created(payload):

    print()

    print("========== EVENT ==========")
    print(events.CUSTOMER_CREATED)
    print(payload)
    print("===========================")


event_bus.subscribe(
    events.CUSTOMER_CREATED,
    customer_created,
)

