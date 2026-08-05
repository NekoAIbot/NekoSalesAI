class NextBestAction:

    def decide(self, customer):

        if customer.lifecycle_stage == "NEW":
            return "INTRODUCE"

        if customer.buying_intent == "HIGH":
            return "SEND_PROPOSAL"

        if customer.engagement_score < 20:
            return "FOLLOW_UP"

        if customer.risk_level == "HIGH":
            return "ESCALATE"

        return "KEEP_NURTURING"


next_best_action = NextBestAction()
