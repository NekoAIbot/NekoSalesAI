"""Quotes — a requirement we priced, kept so it can be bought.

Dynamic pricing creates a problem the three fixed tiers did not have. A catalog
plan could be named in a checkout request safely, because the server looked the
price up itself. A computed price has no catalog entry to look up, so something
has to carry it from the quote to the payment link.

The wrong answer is to let the checkout accept an amount. This table is the
right one: what is stored is the **requirement**, not just the figure, and the
checkout re-prices it server-side at order time. So the amount charged is
always the output of ``app.pricing.complexity.price`` on inputs this server
wrote, and a tampered row is caught rather than charged — ``total_minor`` is
kept only to detect that disagreement, never as the source of the charge.

Distinct from ``Order``, which freezes what was sold. A quote is an answer to
"what would this cost"; most quotes are never bought, and that is fine.
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel


class Quote(BaseModel):
    """A priced requirement, addressable by reference."""

    __tablename__ = "quotes"

    # Opaque and unguessable: a quote reference is the thing a checkout request
    # carries, so a sequential id would let anyone buy at someone else's price.
    reference: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # The storefront org that issued it. Null while the buyer is anonymous —
    # a visitor gets a price before they have an account.
    organization_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    conversation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The requirement, exactly as priced. This is the input the checkout
    # re-prices; the JSON shape is ``RequirementIn``'s.
    requirement_json: Mapped[str] = mapped_column(Text, nullable=False)

    product_type: Mapped[str] = mapped_column(String(40), nullable=False)

    # What we computed at issue time. Compared against a fresh computation at
    # order time so a price change between quote and purchase is caught.
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Quote {self.reference} {self.product_type} {self.total_minor}>"
