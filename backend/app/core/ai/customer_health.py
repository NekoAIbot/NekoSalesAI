class CustomerHealth:

    def evaluate(self, customer):

        if customer.engagement_score >= 80:
            return "EXCELLENT"

        if customer.engagement_score >= 60:
            return "GOOD"

        if customer.engagement_score >= 30:
            return "FAIR"

        return "POOR"


customer_health = CustomerHealth()
