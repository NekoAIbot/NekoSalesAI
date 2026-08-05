class OpportunityAnalyzer:

    def analyze(
        self,
        intent: str,
    ):

        if intent == "BUYING_INTENT":
            return "HIGH"

        if intent == "MEETING":
            return "MEDIUM"

        return "LOW"

