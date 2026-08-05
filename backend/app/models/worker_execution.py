from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func

from app.database.database import Base


class WorkerExecution(Base):
    __tablename__ = "worker_executions"

    id = Column(Integer, primary_key=True, index=True)

    worker_name = Column(String, nullable=False, index=True)

    customer_id = Column(Integer, nullable=True, index=True)

    success = Column(Boolean, default=False)

    started_at = Column(DateTime(timezone=True), nullable=False)

    finished_at = Column(DateTime(timezone=True), nullable=False)

    duration_ms = Column(Integer, default=0)

    payload_json = Column(Text)

    result_json = Column(Text)

    error_message = Column(Text)

    retry_count = Column(Integer, default=0)

    max_retries = Column(Integer, default=3)

    status = Column(String, default="PENDING")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
