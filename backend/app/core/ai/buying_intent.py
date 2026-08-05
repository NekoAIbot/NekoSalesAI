class BuyingIntentEngine:

    def analyze(self, message):
        text = (message or "").lower()

        high = [
            "buy",
            "purchase",
            "price",
            "quote",
            "invoice",
            "contract",
            "demo",
        ]

        medium = [
            "interested",
            "looking",
            "need",
            "help",
            "service",
        ]

        if any(word in text for word in high):
            return "HIGH"

        if any(word in text for word in medium):
            return "MEDIUM"

        return "LOW"


buying_intent = BuyingIntentEngine()
