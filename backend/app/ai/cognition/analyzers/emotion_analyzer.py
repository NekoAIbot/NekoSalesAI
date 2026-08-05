class EmotionAnalyzer:

    def analyze(
        self,
        message: str,
    ):

        text = message.lower()

        if any(word in text for word in [
            "angry",
            "frustrated",
            "terrible",
            "bad",
        ]):
            return "NEGATIVE"

        if any(word in text for word in [
            "thanks",
            "awesome",
            "great",
            "love",
        ]):
            return "POSITIVE"

        return "NEUTRAL"

