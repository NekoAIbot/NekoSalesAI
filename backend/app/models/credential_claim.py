"""Credential Claim Tokens for secure workspace onboarding.

Instead of transmitting raw passwords or permanent API keys in plaintext
via email or exposing them in unauthenticated redirect payloads, provisioning
generates a cryptographically strong single-use setup claim token.

The buyer claims workspace ownership via:
  POST /api/v1/auth/claim-workspace (validate token + buyer email)
  POST /api/v1/auth/complete-setup (set password + generate/retrieve API key)

To survive crashes during email dispatch, `email_sent_at` tracks whether
the delivery email was successfully dispatched. If `None`, the reconciler
or callback handler safely retries dispatch.
"""

from datetime import datetime, UTC
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User


class CredentialClaim(BaseModel):
    """Single-use, time-bounded claim for initial workspace setup."""

    __tablename__ = "credential_claims"

    __table_args__ = (
        UniqueConstraint("order_id", name="uq_credential_claims_order_id"),
    )

    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SHA-256 of the CSPRNG 256-bit token issued to the buyer
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # Encrypted-at-rest token payload for durable retry without link invalidation
    encrypted_token: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Timestamp when setup instructions email was sent (None if dispatch failed/crashed)
    email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Durable dispatch lease & attempt tracking (Correction A)
    dispatch_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    dispatch_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    dispatch_leased_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    dispatch_leased_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    dispatch_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    order: Mapped["Order"] = relationship("Order", foreign_keys=[order_id])
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    @property
    def is_claimed(self) -> bool:
        return self.claimed_at is not None

    @property
    def is_expired(self) -> bool:
        now = datetime.now(UTC)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return now >= exp


def encrypt_claim_token(raw_token: str, secret_key: str) -> str:
    """Encrypt the raw setup token at rest using application SECRET_KEY."""
    import base64
    import hashlib
    from cryptography.fernet import Fernet

    derived_key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())
    return Fernet(derived_key).encrypt(raw_token.encode("utf-8")).decode("utf-8")


def decrypt_claim_token(encrypted_token: str | None, secret_key: str) -> str | None:
    """Decrypt the raw setup token for safe retry. Returns None on failure."""
    if not encrypted_token:
        return None
    import base64
    import hashlib
    from cryptography.fernet import Fernet, InvalidToken

    try:
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())
        return Fernet(derived_key).decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return None

