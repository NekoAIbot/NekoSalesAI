from app.events.event_bus import event_bus


def publish_event(event_name: str, payload: dict):
    event_bus.publish(event_name, payload)
