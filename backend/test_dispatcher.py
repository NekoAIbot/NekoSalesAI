from app.core.events import event_bus
from app.core.events.events import CUSTOMER_CREATED

from app.core.workers import (
    dispatcher,
    register_workers,
)

register_workers()

event_bus.publish(
    CUSTOMER_CREATED,
    {
        "customer_id": 25,
        "name": "Alice",
    },
)

job = dispatcher.next_job()

print(job)

