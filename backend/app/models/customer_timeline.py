from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    JSON,
    DateTime,
    ForeignKey,
)

from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class CustomerTimeline(Base):
    __tablename__ = "customer_timeline"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
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

    event_metadata = Column(JSON)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    customer = relationship("Customer")
