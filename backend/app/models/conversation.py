"""Sales conversation storage.

A conversation is the unit of work for the sales agent: one visitor, one
thread, one lifecycle from first message to closed deal. Messages hang off it,
and so does the reasoning trail — every AI reply records the signals it read
and the rule it followed, because "why did it say that" has to be answerable
after the fact, not just while the process is still running.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

# Lifecycle stages, in order. The agent advances a conversation through these
# and never skips backwards on its own.
STAGE_GREETING = "greeting"
STAGE_DISCOVERY = "discovery"
STAGE_QUALIFIED = "qualified"
STAGE_NEGOTIATING = "negotiating"
STAGE_AWAITING_APPROVAL = "awaiting_approval"
STAGE_READY_TO_BUY = "ready_to_buy"
STAGE_CLOSED_WON = "closed_won"
STAGE_HANDED_OFF = "handed_off"

CONVERSATION_STAGES = (
    STAGE_GREETING,
    STAGE_DISCOVERY,
    STAGE_QUALIFIED,
    STAGE_NEGOTIATING,
    STAGE_AWAITING_APPROVAL,
    STAGE_READY_TO_BUY,
    STAGE_CLOSED_WON,
    STAGE_HANDED_OFF,
)

ROLE_VISITOR = "visitor"
ROLE_AGENT = "agent"
ROLE_HUMAN = "human"

MESSAGE_ROLES = (ROLE_VISITOR, ROLE_AGENT, ROLE_HUMAN)


class Conversation(BaseModel):
    """One visitor's thread with the sales agent."""

    __tablename__ = "conversations"

    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Opaque, unguessable handle given to the browser. The visitor is not
    # logged in, so this is what authorises them to keep posting to their own
    # thread — and nothing else. Never expose the integer id to the widget.
    public_token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # Populated as the visitor volunteers details. All optional: the agent
    # asks, it does not gate the conversation on collecting them.
    visitor_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    visitor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visitor_company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    stage: Mapped[str] = mapped_column(
        String(40),
        default=STAGE_GREETING,
        nullable=False,
        index=True,
    )

    # Set once the visitor is captured as a lead, so the CRM row and the
    # thread stay linked in both directions.
    lead_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Plan the visitor has settled on, by catalog code. Not a foreign key:
    # plans live in version control, not in the database.
    interested_plan_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Set when a human takes over, so the agent stops replying.
    handed_off_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    handoff_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )

    @property
    def is_handed_off(self) -> bool:
        return self.handed_off_at is not None


class Message(BaseModel):
    """A single turn. Agent turns carry the reasoning that produced them."""

    __tablename__ = "conversation_messages"

    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(String(20), nullable=False)

    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Why the agent said this. Stored as JSON text rather than a related
    # table because it is written once with the message, read with the
    # message, and never queried across messages.
    #
    # Shape: {"rule": str, "signals": [str], "grounded_in": [str],
    #         "escalated": bool}
    reasoning_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


Index(
    "ix_conversation_messages_conversation_id_id",
    Message.conversation_id,
    Message.id,
)
