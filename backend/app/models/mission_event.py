from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
)
from sqlalchemy.sql import func

from app.database.base import Base


class MissionEvent(Base):
    __tablename__ = "mission_events"

    id = Column(Integer, primary_key=True, index=True)

    source = Column(
        String(100),
        nullable=False,
        index=True,
    )

    level = Column(
        String(30),
        nullable=False,
        default="INFO",
        index=True,
    )

    title = Column(
        String(255),
        nullable=False,
    )

    message = Column(
        Text,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

