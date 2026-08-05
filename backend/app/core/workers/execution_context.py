from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict
import uuid


@dataclass
class ExecutionContext:
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    worker_name: str = ""
    customer_id: int | None = None
    priority: str = "MEDIUM"
    retry_count: int = 0
    max_retries: int = 3
    started_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)
