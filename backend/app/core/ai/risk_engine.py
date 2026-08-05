class RiskEngine:

    def calculate(self, customer):

        if customer.engagement_score < 10:
            return "HIGH"

        if customer.buying_intent == "LOW":
            return "MEDIUM"

        return "LOW"


risk_engine = RiskEngine()
