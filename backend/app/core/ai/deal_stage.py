class DealStageEngine:

    def update(self, customer):

        if customer.buying_intent == "HIGH":
            customer.lifecycle_stage = "QUALIFIED"

        elif customer.opportunity_score >= 80:
            customer.lifecycle_stage = "PROPOSAL"

        elif customer.engagement_score >= 70:
            customer.lifecycle_stage = "NEGOTIATION"

        elif customer.engagement_score < 10:
            customer.lifecycle_stage = "COLD"

        return customer.lifecycle_stage


deal_stage = DealStageEngine()
