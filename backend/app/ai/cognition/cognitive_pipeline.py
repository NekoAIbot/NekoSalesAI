from app.ai.cognition.analyzers.intent_analyzer import IntentAnalyzer
from app.ai.cognition.analyzers.emotion_analyzer import EmotionAnalyzer
from app.ai.cognition.analyzers.opportunity_analyzer import OpportunityAnalyzer
from app.ai.cognition.analyzers.risk_analyzer import RiskAnalyzer
from app.ai.cognition.analyzers.escalation_analyzer import EscalationAnalyzer

from app.ai.reasoning.confidence_engine import ConfidenceEngine
from app.ai.reasoning.internal_monologue import InternalMonologue
from app.ai.reasoning.action_planner import ActionPlanner

from app.ai.mission_control.mission_control import MissionControl


class CognitivePipeline:

    def __init__(self, db):

        self.db = db

        self.intent = IntentAnalyzer()
        self.emotion = EmotionAnalyzer()
        self.opportunity = OpportunityAnalyzer()
        self.risk = RiskAnalyzer()
        self.escalation = EscalationAnalyzer()

        self.confidence = ConfidenceEngine()
        self.monologue = InternalMonologue()
        self.planner = ActionPlanner()

        self.mission = MissionControl(db)

    def process(
        self,
        customer_id: int,
        message: str,
    ):

        intent = self.intent.analyze(message)

        emotion = self.emotion.analyze(message)

        opportunity = self.opportunity.analyze(intent)

        risk = self.risk.analyze(emotion)

        escalate = self.escalation.analyze(
            opportunity,
            risk,
        )

        confidence = self.confidence.calculate(
            intent,
            emotion,
            opportunity,
            risk,
        )

        thoughts = self.monologue.build(
            customer_id,
            message,
            intent,
            emotion,
            opportunity,
            risk,
            escalate,
        )

        next_action = self.planner.plan(
            confidence,
            escalate,
        )

        self.mission.report(
            source="AI Brain",
            level="INFO",
            title="Reasoning Complete",
            message="\n".join(thoughts),
        )

        return {
            "intent": intent,
            "emotion": emotion,
            "opportunity": opportunity,
            "risk": risk,
            "confidence": confidence,
            "escalate": escalate,
            "next_action": next_action,
            "thoughts": thoughts,
        }

