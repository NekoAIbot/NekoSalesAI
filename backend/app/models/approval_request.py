"""The human approval gate.

When a visitor asks for something outside the published catalog, the agent
does not decide. It records an ApprovalRequest and tells the visitor it is
checking. A human then approves with a specific answer, or declines.

The gate is the product's insurance policy. Anything that could make the
business owe a buyer something — a discount, a custom term, a guarantee —
lands here rather than in a generated sentence. A bug in the agent, or a
prompt injection pasted into the chat box, can at worst create a pending row
for a human to look at.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DECLINED = "declined"

APPROVAL_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_DECLINED)


class ApprovalRequest(BaseModel):
    """One off-script request waiting on a human decision."""

    __tablename__ = "approval_requests"

    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Short label for the queue view, e.g. "Discount request".
    subject: Mapped[str] = mapped_column(String(150), nullable=False)

    # The visitor's message, verbatim. Stored unmodified so the human sees
    # exactly what was asked rather than the agent's paraphrase of it.
    requested: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        default=STATUS_PENDING,
        nullable=False,
        index=True,
    )

    # What the human decided to tell the visitor. Required on approval:
    # approving without an answer would leave the agent with nothing true to
    # say, which is the situation the gate exists to prevent.
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    resolved_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    conversation = relationship("Conversation")

    @property
    def is_pending(self) -> bool:
        return self.status == STATUS_PENDING
