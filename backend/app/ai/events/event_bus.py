class EventBus:

    def __init__(self):
        self.listeners = {}

    def subscribe(self, event_name, callback):

        self.listeners.setdefault(
            event_name,
            []
        ).append(callback)

    def publish(self, event_name, payload):

        callbacks = self.listeners.get(
            event_name,
            []
        )

        for callback in callbacks:
            callback(payload)


event_bus = EventBus()

