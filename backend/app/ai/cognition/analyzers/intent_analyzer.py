class IntentAnalyzer:

    def analyze(
        self,
        message: str,
    ):

        text = message.lower()

        if any(word in text for word in [
            "buy",
            "price",
            "cost",
            "subscribe",
            "purchase",
        ]):
            return "BUYING_INTENT"

        if any(word in text for word in [
            "problem",
            "issue",
            "error",
            "bug",
            "help",
        ]):
            return "SUPPORT"

        if any(word in text for word in [
            "demo",
            "meeting",
            "call",
        ]):
            return "MEETING"

        return "GENERAL"

