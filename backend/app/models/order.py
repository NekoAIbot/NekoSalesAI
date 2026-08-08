"""Orders — the record of what was sold, for how much, to whom.

This is the table that has to survive an argument. When a buyer says "I was
charged the wrong amount", the answer comes from here: the plan code, the
amount in minor units, and the Paystack reference, all frozen at the moment
the payment link was created rather than re-derived later from a catalog that
may since have changed.

That freezing is the point. Prices live in version control and will move. An
order that stored only a plan code would silently re-price itself every time
the catalog was edited, and last quarter's receipts would quietly become
wrong.
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

# An order is created pending, and moves exactly once: to paid when Paystack
# confirms, or to abandoned when it is superseded or expires. There is no
# transition out of paid — a refund is a separate event, not an un-sale.
ORDER_PENDING = "pending"
ORDER_PAID = "paid"
ORDER_ABANDONED = "abandoned"

ORDER_STATUSES = (ORDER_PENDING, ORDER_PAID, ORDER_ABANDONED)


class Order(BaseModel):
    """One attempt to buy one plan."""

    __tablename__ = "orders"

    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    conversation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Paystack's identifier for the transaction. Unique because it is what
    # makes webhook delivery idempotent: Paystack retries, and a retry must
    # find the existing order rather than create a second one.
    paystack_reference: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    # Where we send the buyer to pay. Stored so the link can be re-shown
    # without calling Paystack again.
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Frozen copy of what was sold. plan_code is not a foreign key — plans
    # live in app.catalog, in version control.
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(150), nullable=False)
    billing_period: Mapped[str] = mapped_column(String(20), nullable=False)

    # Integer minor units (kobo). Never a float: 0.1 + 0.2 is not 0.3, and
    # money that is off by a hundredth of a naira is money that is wrong.
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)

    buyer_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    buyer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    buyer_company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        default=ORDER_PENDING,
        nullable=False,
        index=True,
    )

    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Verbatim Paystack payload from the confirming webhook or verification
    # call. Kept because when a payment is disputed, the provider's own words
    # are the evidence, and a summary we wrote is not.
    provider_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    conversation: Mapped["Conversation | None"] = relationship(  # noqa: F821
        back_populates="orders",
    )

    __table_args__ = (
        UniqueConstraint("paystack_reference", name="uq_orders_paystack_reference"),
    )

    @property
    def is_paid(self) -> bool:
        return self.status == ORDER_PAID
