class EngagementEngine:

    def update(self, customer, action):

        if action == "EMAIL_REPLY":
            customer.engagement_score += 15

        elif action == "OPEN_EMAIL":
            customer.engagement_score += 5

        elif action == "CLICK_LINK":
            customer.engagement_score += 20

        elif action == "NO_RESPONSE":
            customer.engagement_score -= 5

        customer.engagement_score = max(
            0,
            min(100, customer.engagement_score),
        )

        return customer.engagement_score


engagement_engine = EngagementEngine()
