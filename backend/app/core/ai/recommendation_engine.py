class RecommendationEngine:

    def recommend(self, customer):

        if customer.buying_intent == "HIGH":
            return [
                "Prepare proposal",
                "Schedule demo",
                "Assign sales representative",
            ]

        if customer.engagement_score > 60:
            return [
                "Send follow-up email",
                "Share product brochure",
            ]

        return [
            "Continue nurturing",
            "Monitor activity",
        ]


recommendation_engine = RecommendationEngine()
