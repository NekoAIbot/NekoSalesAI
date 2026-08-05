from collections import defaultdict
from typing import Callable


class EventBus:

    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(
        self,
        event_name: str,
        handler: Callable,
    ):
        self._handlers[event_name].append(handler)

    def publish(
        self,
        event_name: str,
        payload=None,
    ):
        handlers = self._handlers.get(event_name, [])

        for handler in handlers:
            try:
                handler(payload)
            except Exception as e:
                print(
                    f"[EVENT BUS ERROR] "
                    f"{event_name}: {e}"
                )


event_bus = EventBus()

