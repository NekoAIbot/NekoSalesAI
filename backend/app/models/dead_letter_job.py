from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from app.database.database import Base


class DeadLetterJob(Base):

    __tablename__ = "dead_letter_jobs"

    id = Column(Integer, primary_key=True, index=True)

    worker_name = Column(
        String,
        nullable=False,
        index=True
    )

    customer_id = Column(
        Integer,
        nullable=True,
        index=True
    )

    payload_json = Column(Text)

    error_message = Column(Text)

    status = Column(
        String,
        default="FAILED"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
