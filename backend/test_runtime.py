from app.core.events import event_bus
from app.core.events.events import CUSTOMER_CREATED

from app.core.workers import register_workers
from app.core.runtime import runtime

register_workers()

event_bus.publish(
    CUSTOMER_CREATED,
    {
        "customer_id": 99,
        "name": "Future Customer",
    },
)

runtime.process_next()

