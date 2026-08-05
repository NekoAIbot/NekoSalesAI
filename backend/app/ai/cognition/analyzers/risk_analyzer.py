class RiskAnalyzer:

    def analyze(
        self,
        emotion: str,
    ):

        if emotion == "NEGATIVE":
            return "HIGH"

        return "LOW"

