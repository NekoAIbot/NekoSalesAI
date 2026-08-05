from app.ai.observer import AIObserver


class AIContextBuilder:

    def __init__(self, db):
        self.observer = AIObserver(db)

    def build(self, customer_id: int):

        data = self.observer.observe_customer(customer_id)

        return {
            "customer_id": customer_id,
            "priority": data["priority"],
            "timeline": data["timeline"],
            "tasks": data["tasks"],
            "memories": data["memories"],
            "timeline_count": len(data["timeline"]),
            "task_count": len(data["tasks"]),
            "memory_count": len(data["memories"]),
            "last_scan": data["last_scan"],
        }
