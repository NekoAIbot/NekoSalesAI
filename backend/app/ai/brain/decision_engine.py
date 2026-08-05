from app.ai.context.context_builder import AIContextBuilder
from app.services.ai_decision_log_service import (
    AIDecisionLogService,
)


class DecisionEngine:

    def __init__(self, db):
        self.db = db
        self.context_builder = AIContextBuilder(db)
        self.logger = AIDecisionLogService(db)

    def evaluate(self, customer_id: int):

        context = self.context_builder.build(customer_id)

        priority = context.get("priority")
        timeline_count = context.get("timeline_count", 0)
        task_count = context.get("task_count", 0)
        memory_count = context.get("memory_count", 0)

        decision = {
            "customer_id": customer_id,
            "action": "NONE",
            "reason": "No action required.",
            "priority": "LOW",
            "notify_owner": False,
            "create_task": False,
            "generate_summary": False,
            "handoff": False,
        }

        if priority:

            score = priority.score

            if score >= 90:
                decision.update({
                    "action": "ESCALATE_OWNER",
                    "reason": "Critical customer detected.",
                    "priority": "CRITICAL",
                    "notify_owner": True,
                    "handoff": True,
                })

            elif score >= 75:
                decision.update({
                    "action": "FOLLOW_UP",
                    "reason": "High-value customer.",
                    "priority": "HIGH",
                    "create_task": True,
                })

            elif score >= 50:
                decision.update({
                    "action": "KEEP_NURTURING",
                    "reason": "Continue AI conversation.",
                    "priority": "MEDIUM",
                })

        if timeline_count >= 100:
            decision.update({
                "action": "GENERATE_SUMMARY",
                "reason": "Long customer history detected.",
                "generate_summary": True,
            })

        if task_count >= 20:
            decision.update({
                "action": "TASK_CLEANUP",
                "reason": "Too many pending AI tasks.",
            })

        if memory_count >= 500:
            decision.update({
                "action": "MEMORY_COMPRESSION",
                "reason": "Customer memory becoming large.",
            })

        self._log_decision(decision)

        return decision

    def _log_decision(self, decision):

        self.logger.log(decision)

        print("[AI DECISION]", decision)

