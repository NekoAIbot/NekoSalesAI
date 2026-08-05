from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)

from sqlalchemy.sql import func

from app.database.base import Base


class AITask(Base):

    __tablename__ = "ai_tasks"

    id = Column(Integer, primary_key=True, index=True)

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_type = Column(String(100), nullable=False)

    title = Column(String(255), nullable=False)

    description = Column(Text)

    priority = Column(String(30), default="medium")

    status = Column(String(30), default="pending")

    assigned_to = Column(String(100), default="AI")

    due_at = Column(DateTime(timezone=True))

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
