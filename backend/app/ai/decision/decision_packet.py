from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DecisionPacket:

    customer_id: int

    timestamp: datetime = field(
        default_factory=datetime.utcnow
    )

    message: str = ""

    intent: str = ""

    emotion: str = ""

    opportunity: str = ""

    risk: str = ""

    confidence: int = 0

    escalate: bool = False

    next_action: str = ""

    response: str = ""

    summary: str = ""

    thoughts: list[str] = field(
        default_factory=list
    )

