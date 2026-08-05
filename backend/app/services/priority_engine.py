from datetime import datetime, timezone


class PriorityEngine:

    def calculate(
        self,
        *,
        purchase_probability: float = 0,
        deal_value: float = 0,
        sentiment: float = 0,
        unread_messages: int = 0,
        inactivity_hours: int = 0,
        escalation: bool = False,
    ):

        score = 0.0
        reasons = []

        score += purchase_probability * 0.40

        score += min(deal_value / 100000, 20)

        score += sentiment * 10

        score += unread_messages * 3

        if inactivity_hours > 24:
            score += 10
            reasons.append("Customer inactive")

        if inactivity_hours > 72:
            score += 20
            reasons.append("Lead becoming cold")

        if escalation:
            score += 40
            reasons.append("Human attention required")

        score = min(score, 100)

        if score >= 90:
            priority = "CRITICAL"
        elif score >= 75:
            priority = "HIGH"
        elif score >= 50:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        return {
            "score": round(score, 2),
            "priority": priority,
            "reasons": reasons,
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

