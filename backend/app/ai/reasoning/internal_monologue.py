from datetime import datetime


class InternalMonologue:

    def build(
        self,
        customer_id: int,
        message: str,
        intent: str,
        emotion: str,
        opportunity: str,
        risk: str,
        escalate: bool,
    ):

        thoughts = []

        thoughts.append(
            f"[{datetime.utcnow()}] Customer #{customer_id}"
        )

        thoughts.append(
            f"Incoming message: {message}"
        )

        thoughts.append(
            f"Detected intent: {intent}"
        )

        thoughts.append(
            f"Detected emotion: {emotion}"
        )

        thoughts.append(
            f"Opportunity score: {opportunity}"
        )

        thoughts.append(
            f"Risk level: {risk}"
        )

        if escalate:
            thoughts.append(
                "Decision: Escalate to owner."
            )
        else:
            thoughts.append(
                "Decision: Continue autonomously."
            )

        return thoughts

