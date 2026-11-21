"""Distributed System Leases for multi-worker coordination.

Prevents split-brain execution across multiple web application workers
(e.g., Uvicorn workers on Render or multi-pod container clusters).

Instead of raw database connection-level advisory locks (which are tied to
physical connection PIDs and prone to connection-pool leakage), SystemLease
records durable lease ownership in a database table with an explicit expiry.
If a worker crashes or is killed, the lease naturally expires after its TTL.
"""

from datetime import datetime, UTC

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SystemLease(Base):
    """A named distributed lease with a time-to-live."""

    __tablename__ = "system_leases"

    lease_name: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    acquired_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Monotonically increasing fencing token for distributed ownership fencing (Correction B)
    fencing_token: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    @property
    def is_expired(self) -> bool:
        now = datetime.now(UTC)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return now >= exp
