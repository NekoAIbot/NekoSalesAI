from app.ai.decision.decision_packet import DecisionPacket


class DecisionBuilder:

    def build(
        self,
        customer_id: int,
        message: str,
    ):

        return DecisionPacket(
            customer_id=customer_id,
            message=message,
        )

