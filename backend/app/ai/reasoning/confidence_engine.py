class ConfidenceEngine:

    def calculate(
        self,
        intent: str,
        emotion: str,
        opportunity: str,
        risk: str,
    ):

        confidence = 50

        if intent == "BUYING_INTENT":
            confidence += 20

        if opportunity == "HIGH":
            confidence += 15

        if emotion == "POSITIVE":
            confidence += 10

        if risk == "HIGH":
            confidence -= 25

        confidence = max(0, min(confidence, 100))

        return confidence

