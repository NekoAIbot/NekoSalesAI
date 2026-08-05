from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class AIDecisionLog(Base):
    __tablename__ = "ai_decision_logs"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action = Column(String(100), nullable=False, index=True)

    priority = Column(String(30), nullable=False)

    reason = Column(Text)

    decision_data = Column(Text)

    source = Column(
        String(100),
        default="DecisionEngine",
        nullable=False,
    )

    executed = Column(
        String(20),
        default="PENDING",
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    customer = relationship("Customer")

