"""The wire format for a quote request.

Note what is absent: there is no amount, price or total field anywhere in this
module. A caller describes *what they want built* and the server computes the
figure.

The currently purchasable catalog:
- AI Sales Agent (sales_agent)
- AI Support Agent (support_agent)
- Workforce (workforce_agent)
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

# A ceiling on list *size*, far above any requirement we would quote.
MAX_LIST_ITEMS = 200


class RequirementIn(BaseModel):
    """What a buyer wants built.

    Shape is checked here; policy is not. This layer answers "is this a
    requirement at all" — right types, no negative counts, nothing absurdly
    large — and leaves "would we quote for it" to ``Requirement``.

    Workflow steps are intentionally NOT part of this schema.
    The current customer flow does not expose workflow-step configuration.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    product_type: str = Field(default=PRODUCT_SALES_AGENT, max_length=40)
    products: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    channels: tuple[str, ...] = Field(default=(CHANNEL_WEB,), max_length=MAX_LIST_ITEMS)
    integrations: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    languages: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    monthly_conversations: int = Field(default=500, ge=0)

    def to_requirement(self) -> Requirement:
        """Build the priceable requirement.

        ``products`` takes precedence when provided, so the frontend can send
        an explicit list for bundle selections without inventing a fake
        ``product_type`` string.
        """
        products = tuple(
            code.strip() for code in self.products if code.strip()
        ) or (self.product_type,)

        return Requirement(
            product_type=self.product_type,
            products=products,
            channels=tuple(c.lower() for c in self.channels),
            integrations=self.integrations,
            languages=self.languages,
            monthly_conversations=self.monthly_conversations,
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
    """A price and the whole reason for it."""

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
