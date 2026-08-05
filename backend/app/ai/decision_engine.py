from dataclasses import dataclass


@dataclass
class Decision:

    action: str

    confidence: float

    reason: str

    notify_owner: bool = False

    escalate: bool = False


class AIDecisionEngine:

    def evaluate(self, event):

        event_type = event.event_type.lower()

        payload = event.payload.lower()


        if "refund" in payload:

            return Decision(
                action="ESCALATE",
                confidence=0.99,
                reason="Refund request detected.",
                notify_owner=True,
                escalate=True,
            )


        if "angry" in payload:

            return Decision(
                action="ESCALATE",
                confidence=0.95,
                reason="Customer frustration detected.",
                notify_owner=True,
                escalate=True,
            )


        if "buy" in payload:

            return Decision(
                action="FOLLOW_UP",
                confidence=0.94,
                reason="High buying intent detected.",
            )


        if "price" in payload:

            return Decision(
                action="PRICE_OBJECTION",
                confidence=0.88,
                reason="Pricing objection detected.",
            )


        return Decision(
            action="CONTINUE_AUTONOMOUSLY",
            confidence=0.90,
            reason="No human intervention required.",
        )
