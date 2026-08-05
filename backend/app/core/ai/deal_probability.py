class DealProbability:

    def predict(self, customer):

        score = (
            customer.opportunity_score * 0.5 +
            customer.engagement_score * 0.3
        )

        if customer.buying_intent == "HIGH":
            score += 20

        return min(round(score), 100)


deal_probability = DealProbability()
