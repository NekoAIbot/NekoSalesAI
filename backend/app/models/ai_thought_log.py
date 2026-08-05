from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
)
from sqlalchemy.sql import func

from app.database.base import Base


class AIThoughtLog(Base):
    __tablename__ = "ai_thought_logs"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    stage = Column(
        String(50),
        nullable=False,
        index=True,
    )

    message = Column(
        Text,
        nullable=False,
    )

    confidence = Column(
        Float,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

