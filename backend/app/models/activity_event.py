from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

from app.database.database import Base


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(Integer, index=True, nullable=True)

    event_type = Column(String, nullable=False, index=True)

    title = Column(String, nullable=False)

    description = Column(Text)

    source = Column(String, default="AI")

    priority = Column(String, default="MEDIUM")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
