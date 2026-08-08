"""Scheduled post-sale follow-ups.

The loop that runs after the money lands. A customer who paid and never
switched their widget on is a refund in three weeks' time, so something has to
notice and say so — but that something is a calendar and a set of rules, not
another model deciding what it feels like sending.

Each row is one message, owed to one customer, on one date, because one named
rule fired. All four of those are columns. That is the whole design: a
follow-up you cannot explain is a follow-up you should not send.

Two things are deliberately *not* here.

There is no confidence or engagement score. The rules read facts — has this
workspace had a conversation, was the API key ever used — and a fact does not
need a percentage attached to look more decisive than it is.

There is no generated prose. ``subject`` and ``body`` are rendered from
templates in app.followups.rules against values read from the customer's own
record. A follow-up cannot invent a discount, a feature or a deadline for the
same reason the sales agent cannot: it has no mechanism for producing a
sentence nobody wrote.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

STATUS_SCHEDULED = "scheduled"
STATUS_SENT = "sent"
STATUS_CANCELLED = "cancelled"

FOLLOW_UP_STATUSES = (STATUS_SCHEDULED, STATUS_SENT, STATUS_CANCELLED)


class FollowUp(BaseModel):
    """One rule-scheduled message to one customer."""

    __tablename__ = "follow_ups"

    __table_args__ = (
        # The scheduler is expected to run repeatedly — on a cron, on a
        # deploy, twice by accident. Scheduling is therefore idempotent by
        # constraint rather than by hoping the caller checks first: a given
        # rule can exist exactly once per workspace.
        UniqueConstraint(
            "workspace_profile_id",
            "rule_code",
            name="uq_follow_ups_workspace_rule",
        ),
    )

    # The seller's organization, not the buyer's. This is what scopes the
    # follow-up queue on the sales desk, and it is the tenant boundary.
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    workspace_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspace_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Which rule scheduled this, e.g. "day_1_activation". Names the code in
    # app.followups.rules that produced the row, so an odd-looking message in
    # the queue can be traced to the branch that wrote it.
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    # Days after the workspace went live. Stored alongside due_at because
    # due_at alone loses the intent once a date passes.
    day_offset: Mapped[int] = mapped_column(Integer, nullable=False)

    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=STATUS_SCHEDULED,
        nullable=False,
        index=True,
    )

    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Why this is being sent, in the same shape the sales agent uses: the
    # rule, the signals read, and what they were read from. Serialised
    # Reasoning. Shown next to the message on the desk so whoever sends it
    # can see the basis before it goes out.
    reasoning_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Set when a rule is overtaken by events — the customer activated before
    # the "you have not activated" nudge came due. Kept rather than deleted,
    # because "we decided not to send this, and here is why" is worth more
    # than a missing row.
    cancelled_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    workspace_profile: Mapped["WorkspaceProfile"] = relationship()  # noqa: F821

    @property
    def is_open(self) -> bool:
        return self.status == STATUS_SCHEDULED
