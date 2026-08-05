class EscalationAnalyzer:

    def analyze(
        self,
        opportunity: str,
        risk: str,
    ):

        if risk == "HIGH":
            return True

        if opportunity == "HIGH":
            return False

        return False

