class OpportunityScore:

    def score(self, customer):

        score = 0

        if customer.buying_intent == "HIGH":
            score += 40

        if customer.engagement_score >= 50:
            score += 30

        if customer.company:
            score += 15

        if customer.job_title:
            score += 15

        return min(score, 100)


opportunity_score = OpportunityScore()
