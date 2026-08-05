from app.ai.brain.decision_engine import DecisionEngine
from app.ai.mission_control.mission_control import MissionControl


class SchedulerWorker:

    def __init__(self, db):

        self.db = db
        self.decision_engine = DecisionEngine(db)
        self.mission_control = MissionControl(db)

    def process_customer(self, customer_id: int):

        decision = self.decision_engine.evaluate(customer_id)

        self.mission_control.report(
            source="DecisionEngine",
            level="INFO",
            title="Customer Evaluated",
            message=str(decision),
        )

        return decision

