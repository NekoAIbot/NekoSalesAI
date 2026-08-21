"""The wire format for a quote request.

Note what is absent: there is no amount, price or total field anywhere in this
module. A caller describes *what they want built* and the server computes the
figure. A request that could carry its own price would be a way to buy an AI
product for a naira.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.pricing.complexity import (
    CHANNEL_WEB,
    PRODUCT_SALES_AGENT,
    LineItem,
    Quote,
    Requirement,
)

# A ceiling on list *size*, far above any requirement we would quote. This is a
# guard against an absurd payload, not a business rule: the real ceilings live
# in ``Requirement`` and are quoted back to the buyer as prose (see below).
MAX_LIST_ITEMS = 200


class RequirementIn(BaseModel):
    """What a buyer wants built.

    Shape is checked here; policy is not. This layer answers "is this a
    requirement at all" — right types, no negative counts, nothing absurdly
    large — and leaves "would we quote for it" to ``Requirement``, which is the
    only place that knows the answer and the only place with a sentence to
    explain it.

    That division matters because the two layers fail differently. A bound
    duplicated here fails as a 422 naming a field, which is not something a
    buyer can act on; the same bound in ``Requirement`` raises ``PricingError``
    with copy written to be read ("More than 10 integrations needs a human to
    scope it"), which the route returns as a 400 and the builder shows verbatim.
    Duplicating a ceiling here would shadow that message with a worse one.

    ``Requirement`` stays independently safe either way, so a caller that never
    touches HTTP is no less protected by the ceilings living there.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    product_type: str = Field(default=PRODUCT_SALES_AGENT, max_length=40)
    channels: tuple[str, ...] = Field(default=(CHANNEL_WEB,), max_length=MAX_LIST_ITEMS)
    integrations: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    languages: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    monthly_conversations: int = Field(default=500, ge=0)
    workflow_steps: int = Field(default=0, ge=0)

    def to_requirement(self) -> Requirement:
        """Build the priceable requirement.

        ``discount_percent`` is not passed through and is not a field above. A
        buyer asking for their own discount would be setting our price; the
        approvals layer is what grants one.
        """
        return Requirement(
            product_type=self.product_type,
            channels=tuple(c.lower() for c in self.channels),
            integrations=self.integrations,
            languages=self.languages,
            monthly_conversations=self.monthly_conversations,
            workflow_steps=self.workflow_steps,
        )


class LineItemOut(BaseModel):
    dimension: str
    label: str
    amount_minor: int
    display_amount: str

    @classmethod
    def from_line_item(cls, item: LineItem) -> LineItemOut:
        return cls(
            dimension=item.dimension,
            label=item.label,
            amount_minor=item.amount_minor,
            display_amount=item.display_amount,
        )


class QuoteOut(BaseModel):
    """A price and the whole reason for it.

    The line items are not decoration. A buyer who asks "why is it this much"
    gets this list, which is the same list the total is summed from.

    ``reference`` is what the checkout accepts. It names a stored requirement,
    not an amount: redeeming it re-runs the pricing engine, so a reference is
    worth whatever the requirement prices at and nothing else.
    """

    reference: str | None = None
    product_type: str
    product_name: str
    currency: str
    billing_period: str
    monthly_conversation_limit: int

    line_items: tuple[LineItemOut, ...]
    subtotal_minor: int
    discount_minor: int
    total_minor: int
    display_total: str

    @classmethod
    def from_quote(cls, quote: Quote, *, reference: str | None = None) -> QuoteOut:
        return cls(
            reference=reference,
            product_type=quote.product_type,
            product_name=quote.product_name,
            currency=quote.currency,
            billing_period=quote.billing_period,
            monthly_conversation_limit=quote.monthly_conversation_limit,
            line_items=tuple(
                LineItemOut.from_line_item(item) for item in quote.line_items
            ),
            subtotal_minor=quote.subtotal_minor,
            discount_minor=quote.discount_minor,
            total_minor=quote.total_minor,
            display_total=quote.display_total,
        )
