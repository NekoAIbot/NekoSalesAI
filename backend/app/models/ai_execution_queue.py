from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
)
from sqlalchemy.sql import func

from app.database.base import Base


class AIExecutionQueue(Base):
    __tablename__ = "ai_execution_queue"

    id = Column(Integer, primary_key=True, index=True)

    action = Column(String(100), nullable=False, index=True)

    payload = Column(Text, nullable=False)

    status = Column(
        String(30),
        default="PENDING",
        nullable=False,
        index=True,
    )

    attempts = Column(
        Integer,
        default=0,
        nullable=False,
    )

    error = Column(Text)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    processed_at = Column(
        DateTime(timezone=True),
    )

