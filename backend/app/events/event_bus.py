from collections import defaultdict
from typing import Callable, Any


class EventBus:

    def __init__(self):
        self.listeners = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable):
        self.listeners[event_name].append(callback)

    def publish(self, event_name: str, payload: Any):

        if event_name not in self.listeners:
            return

        for callback in self.listeners[event_name]:
            callback(payload)


event_bus = EventBus()
