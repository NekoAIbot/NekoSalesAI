"""Pending email+code handshake for telegram /connect.

A chat that wants to link has no web session yet, so it cannot mint a link
token from the dashboard. Instead the bot asks for the account email, mails a
code, and matches the reply. Rows are short-lived and single-purpose; the code
and the account identity are only ever stored hashed except the email, which
we need in the clear to send the temp password instructions.
"""

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel

CONNECT_CODE_TTL_MINUTES = 10
CONNECT_MAX_ATTEMPTS = 3


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class TelegramConnectCode(BaseModel):
    __tablename__ = "telegram_connect_codes"

    chat_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @classmethod
    def fresh(cls, chat_id: str, email: str, code: str) -> "TelegramConnectCode":
        now = datetime.now(timezone.utc)
        return cls(
            chat_id=chat_id,
            email=email,
            email_hash=hash_value(email.strip().lower()),
            code_hash=hash_value(code.strip()),
            expires_at=now + timedelta(minutes=CONNECT_CODE_TTL_MINUTES),
        )

    def matches(self, code: str) -> bool:
        return self.code_hash == hash_value(code.strip())

    def expired(self) -> bool:
        expiry = self.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry <= datetime.now(timezone.utc)
