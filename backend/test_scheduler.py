import time

from app.core.events import event_bus
from app.core.events.events import CUSTOMER_CREATED

from app.core.workers import register_workers
from app.core.scheduler import heartbeat

register_workers()

heartbeat.start()

event_bus.publish(
    CUSTOMER_CREATED,
    {
        "customer_id": 50,
        "name": "Scheduler Test",
    },
)

time.sleep(20)

