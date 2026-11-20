"""Distributed Lease Service for worker coordination.

Provides robust, multi-process coordination backed by the `system_leases` table.
Immune to connection pool resets, process crashes (via lease TTL expiry), and
fully portable across PostgreSQL and SQLite.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, UTC

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.models.system_lease import SystemLease

logger = get_logger(__name__)


class LeaseService:
    """Manages distributed leases in the database."""

    def __init__(self, db: Session, worker_id: str | None = None):
        self.db = db
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"

    def acquire_lease(self, lease_name: str, ttl_seconds: int = 90) -> bool:
        """Attempt to acquire or renew a distributed lease.

        Returns True if the lease was successfully acquired or renewed by this worker.
        Returns False if another worker currently holds an unexpired lease.
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        # Ensure the lease row exists
        existing = self.db.execute(
            select(SystemLease).where(SystemLease.lease_name == lease_name)
        ).scalar_one_or_none()

        if existing is None:
            try:
                lease = SystemLease(
                    lease_name=lease_name,
                    acquired_by=self.worker_id,
                    acquired_at=now,
                    expires_at=expires_at,
                )
                self.db.add(lease)
                self.db.commit()
                return True
            except Exception:
                self.db.rollback()
                # Another worker raced to insert the row; fall through to atomic conditional update

        # Atomic conditional update: acquire if lease has expired or if already owned by this worker
        stmt = (
            update(SystemLease)
            .where(
                SystemLease.lease_name == lease_name,
                or_(
                    SystemLease.expires_at < now,
                    SystemLease.acquired_by == self.worker_id,
                ),
            )
            .values(
                acquired_by=self.worker_id,
                acquired_at=now,
                expires_at=expires_at,
            )
            .execution_options(synchronize_session=False)
        )
        res = self.db.execute(stmt)
        if res.rowcount > 0:
            self.db.commit()
            return True

        self.db.rollback()
        return False

    def release_lease(self, lease_name: str) -> None:
        """Release the lease immediately if held by this worker."""
        now = datetime.now(UTC)
        stmt = (
            update(SystemLease)
            .where(
                SystemLease.lease_name == lease_name,
                SystemLease.acquired_by == self.worker_id,
            )
            .values(expires_at=now)
            .execution_options(synchronize_session=False)
        )
        self.db.execute(stmt)
        self.db.commit()
