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
    MAX_INTEGRATIONS,
    MAX_LANGUAGES,
    MAX_QUOTABLE_CONVERSATIONS,
    MAX_WORKFLOW_STEPS,
    PRODUCT_SALES_AGENT,
    LineItem,
    Quote,
    Requirement,
)


class RequirementIn(BaseModel):
    """What a buyer wants built.

    The bounds here mirror ``Requirement``'s own. Duplicated deliberately: this
    layer turns an over-large request into a 422 with a field name, while the
    dataclass stays independently safe for callers that never touch HTTP.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    product_type: str = Field(default=PRODUCT_SALES_AGENT, max_length=40)
    channels: tuple[str, ...] = (CHANNEL_WEB,)
    integrations: tuple[str, ...] = Field(default=(), max_length=MAX_INTEGRATIONS)
    languages: tuple[str, ...] = Field(default=(), max_length=MAX_LANGUAGES)
    monthly_conversations: int = Field(
        default=500, ge=0, le=MAX_QUOTABLE_CONVERSATIONS
    )
    workflow_steps: int = Field(default=0, ge=0, le=MAX_WORKFLOW_STEPS)

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
