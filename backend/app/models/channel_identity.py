"""Who a Telegram chat id or WhatsApp number is, between messages.

A visitor in a browser carries their thread in a cookie-like ``public_token``
handed to them when the widget opened. Someone messaging on Telegram or WhatsApp
carries nothing: every delivery arrives with a chat id and no memory. Without a
row like this, each message would open a fresh conversation, the agent would
greet the same person forever, and the stage machine — the thing that decides
whether a buyer has been qualified — would never advance past the first turn.

So this is the memory. One row per (organization, channel, external id), pointing
at the conversation that person is having. The unique constraint is what makes it
a *mapping* rather than a log: two rows for the same chat id would mean two live
threads for one person, and whichever the code found first would win.

Scoped by organization because the same phone number may one day talk to two
different customers' agents, and those are two different conversations with two
different catalogs behind them. Nothing today creates rows for more than the
storefront, but a mapping keyed only on the chat id would have to be migrated
on the day that changes.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

# The platforms a person can reach the agent on. Deliberately the same strings
# as WorkspaceProfile's follow-up channels — one vocabulary for "which
# messenger", whether the message is going out or coming in.
CHANNEL_TELEGRAM = "telegram"
CHANNEL_WHATSAPP = "whatsapp"

INBOUND_CHANNELS = (CHANNEL_TELEGRAM, CHANNEL_WHATSAPP)


class ChannelIdentity(BaseModel):
    """A messenger account, and the conversation it is currently in."""

    __tablename__ = "channel_identities"

    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    channel: Mapped[str] = mapped_column(String(20), nullable=False)

    # Telegram's chat id, or the WhatsApp number in the form Meta reports it
    # (``wa_id`` — digits, no plus). Stored as text: a chat id is an opaque
    # handle that happens to look numeric, and Telegram's are already wider
    # than a 32-bit int.
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)

    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Whatever the platform volunteered — a Telegram display name, a WhatsApp
    # profile name. Not trusted for anything; it is a courtesy so a human
    # reading the desk sees a name rather than a number.
    display_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    conversation: Mapped["Conversation"] = relationship()  # noqa: F821

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "channel",
            "external_id",
            name="uq_channel_identity_per_org",
        ),
    )
