from app.ai.context.context_builder import AIContextBuilder
from app.ai.brain.decision_engine import DecisionEngine
from app.ai.cognition.cognitive_pipeline import CognitivePipeline
from app.ai.mission_control.mission_control import MissionControl


class ConversationOrchestrator:

    def __init__(self, db):

        self.db = db

        self.context = AIContextBuilder(db)
        self.pipeline = CognitivePipeline(db)
        self.decision = DecisionEngine(db)
        self.mission = MissionControl(db)

    def process(
        self,
        customer_id: int,
        message: str,
    ):

        self.mission.report(
            source="Conversation",
            level="INFO",
            title="Incoming Message",
            message=message,
        )

        context = self.context.build(customer_id)

        thoughts = self.pipeline.process(
            customer_id,
            message,
        )

        decision = self.decision.evaluate(customer_id)

        self.mission.report(
            source="Decision Engine",
            level="INFO",
            title="Final Decision",
            message=str(decision),
        )

        return {
            "context": context,
            "thoughts": thoughts,
            "decision": decision,
        }

