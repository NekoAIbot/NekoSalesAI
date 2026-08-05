from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.base import Base


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

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
        nullable=True,
        index=True,
    )

    event_type = Column(
        String(100),
        nullable=False,
        index=True,
    )

    title = Column(
        String(255),
        nullable=False,
    )

    description = Column(Text)

    actor = Column(
        String(100),
        default="System",
    )

    source = Column(
        String(100),
        default="AI",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    organization = relationship("Organization")
    customer = relationship("Customer")
