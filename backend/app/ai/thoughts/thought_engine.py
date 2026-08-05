from datetime import datetime


class ThoughtEngine:

    def __init__(self):
        self.steps = []

    def record(
        self,
        stage: str,
        message: str,
        confidence: float | None = None,
    ):
        self.steps.append(
            {
                "time": datetime.utcnow().isoformat(),
                "stage": stage,
                "message": message,
                "confidence": confidence,
            }
        )

    def observe(self, message: str):
        self.record("OBSERVE", message)

    def understand(self, message: str):
        self.record("UNDERSTAND", message)

    def remember(self, message: str):
        self.record("REMEMBER", message)

    def predict(self, message: str):
        self.record("PREDICT", message)

    def decide(self, message: str):
        self.record("DECIDE", message)

    def act(self, message: str):
        self.record("ACT", message)

    def verify(self, message: str):
        self.record("VERIFY", message)

    def learn(self, message: str):
        self.record("LEARN", message)

    def dump(self):
        return self.steps

