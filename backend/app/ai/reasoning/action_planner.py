class ActionPlanner:

    def plan(
        self,
        confidence: int,
        escalate: bool,
    ):

        if escalate:
            return "Notify owner immediately."

        if confidence >= 85:
            return "Proceed with autonomous sales conversation."

        if confidence >= 70:
            return "Continue conversation and collect more information."

        return "Ask clarifying questions."

