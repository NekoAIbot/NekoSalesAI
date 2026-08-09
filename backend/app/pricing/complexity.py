"""Pricing an AI product from what it has to do, not from a fixed tier.

The three storefront tiers priced a single product. A factory that builds a
dental clinic's booking agent and a fintech's support desk from the same engine
cannot bill both from one list, because the work genuinely differs: more
channels, more integrations, more languages, more volume.

Two rules make this safe to put in front of a buyer.

**The price is computed, never accepted.** Nothing in this module reads an
amount from a caller. A requirement is scored into line items and the line
items are summed in integer minor units, so the figure the agent quotes is one
this repo can derive again from the same inputs.

**Every figure is attributable.** A quote carries its line items, each naming
the dimension that produced it. A buyer asking "why is it this much" gets the
breakdown rather than a number, and a discount is applied as a visible line
rather than by quietly editing the total.

Nothing here is a promise about delivery. Scoring a requirement says what it
would cost to build, not that it exists — provisioning is what makes it real.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.products.config import Plan, format_money

CURRENCY_NGN = "NGN"

# The dimension each line item is attributed to. Named constants because the
# quote's own arithmetic keys off them — a typo'd string would silently drop a
# line out of the subtotal or leave a discount in it.
DIMENSION_BASE = "base"
DIMENSION_CHANNEL = "channel"
DIMENSION_INTEGRATION = "integration"
DIMENSION_LANGUAGE = "language"
DIMENSION_VOLUME = "volume"
DIMENSION_WORKFLOW = "workflow"
DIMENSION_DISCOUNT = "discount"

# The base a product starts at, before anything is added for scope. Keyed by
# the kind of AI being built, because a support agent that answers from a
# knowledge base is not the same build as a sales agent that quotes and closes.
PRODUCT_SALES_AGENT = "sales_agent"
PRODUCT_SUPPORT_AGENT = "support_agent"

PRODUCT_BASE_MINOR: dict[str, int] = {
    PRODUCT_SALES_AGENT: 25_000_00,
    PRODUCT_SUPPORT_AGENT: 18_000_00,
}

PRODUCT_NAMES: dict[str, str] = {
    PRODUCT_SALES_AGENT: "AI Sales Representative",
    PRODUCT_SUPPORT_AGENT: "AI Support Agent",
}

# Channels the engine can actually answer on. The web widget is included in
# the base because every product ships with it; the rest are real integration
# work, so they carry a real add.
CHANNEL_WEB = "web"
CHANNEL_TELEGRAM = "telegram"
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_EMAIL = "email"

CHANNEL_ADD_MINOR: dict[str, int] = {
    CHANNEL_WEB: 0,
    CHANNEL_TELEGRAM: 4_000_00,
    CHANNEL_WHATSAPP: 8_000_00,
    CHANNEL_EMAIL: 3_000_00,
}

CHANNEL_NAMES: dict[str, str] = {
    CHANNEL_WEB: "Web widget",
    CHANNEL_TELEGRAM: "Telegram",
    CHANNEL_WHATSAPP: "WhatsApp",
    CHANNEL_EMAIL: "Email",
}

# Anything that has to talk to a system we do not control: a CRM, a calendar,
# a payment provider beyond the built-in one.
INTEGRATION_ADD_MINOR = 5_000_00
MAX_INTEGRATIONS = 10

# A second language is translation and testing work, not a config flag.
LANGUAGE_ADD_MINOR = 3_500_00
MAX_LANGUAGES = 6

# Conversation volume. Bands rather than per-message pricing, so a buyer can
# tell what they will pay before they know their traffic.
VOLUME_BANDS: tuple[tuple[int, int], ...] = (
    (500, 0),
    (2_000, 6_000_00),
    (10_000, 20_000_00),
    (50_000, 70_000_00),
)

# Above the largest band we do not quote. A number invented past the last band
# we have actually costed would be a fabricated price.
MAX_QUOTABLE_CONVERSATIONS = VOLUME_BANDS[-1][0]

# Human approval gates and custom workflow steps: each one is a rule someone
# has to specify, build and test.
WORKFLOW_STEP_ADD_MINOR = 2_500_00
MAX_WORKFLOW_STEPS = 20

BILLING_MONTH = "month"


class PricingError(ValueError):
    """A requirement cannot be priced. Carries what to tell the buyer."""


@dataclass(frozen=True)
class LineItem:
    """One reason the price is what it is."""

    # The dimension responsible: "base", "channel", "integration", and so on.
    # A buyer sees the label; the trail sees the dimension.
    dimension: str
    label: str
    amount_minor: int

    @property
    def display_amount(self) -> str:
        return format_money(self.amount_minor, CURRENCY_NGN)


@dataclass(frozen=True)
class Requirement:
    """What a buyer wants built, in the terms the pricing understands.

    Every field is bounded. An unbounded requirement would either produce an
    unbounded price or make the quote depend on how much text someone pasted,
    and neither is a figure we could defend.
    """

    product_type: str = PRODUCT_SALES_AGENT
    channels: tuple[str, ...] = (CHANNEL_WEB,)
    integrations: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    monthly_conversations: int = 500
    workflow_steps: int = 0

    # Applied as a visible line, and only within the ceiling the approvals
    # layer already enforces. Never a silent edit to the total.
    discount_percent: int = 0

    def __post_init__(self) -> None:
        if self.product_type not in PRODUCT_BASE_MINOR:
            raise PricingError(
                f"{self.product_type!r} is not a product this factory builds yet."
            )

        unknown = [c for c in self.channels if c not in CHANNEL_ADD_MINOR]
        if unknown:
            raise PricingError(
                f"We cannot answer on {', '.join(sorted(unknown))} yet, so we "
                "will not quote for it."
            )

        if len(self.integrations) > MAX_INTEGRATIONS:
            raise PricingError(
                f"More than {MAX_INTEGRATIONS} integrations needs a human to "
                "scope it. We will not auto-quote that."
            )

        if len(self.languages) > MAX_LANGUAGES:
            raise PricingError(f"At most {MAX_LANGUAGES} languages per product.")

        if self.monthly_conversations < 0:
            raise PricingError("Conversation volume cannot be negative.")

        if self.monthly_conversations > MAX_QUOTABLE_CONVERSATIONS:
            # Deliberately a refusal rather than an extrapolation. We have not
            # costed this volume, so any figure would be made up.
            raise PricingError(
                f"Above {MAX_QUOTABLE_CONVERSATIONS:,} conversations a month we "
                "price by hand. Talk to us and we will quote properly."
            )

        if not 0 <= self.workflow_steps <= MAX_WORKFLOW_STEPS:
            raise PricingError(
                f"Custom workflow steps must be between 0 and {MAX_WORKFLOW_STEPS}."
            )

        if not 0 <= self.discount_percent <= 100:
            raise PricingError("A discount must be between 0 and 100 percent.")

    @property
    def billable_channels(self) -> tuple[str, ...]:
        """Channels in a stable order, deduplicated.

        Asking for WhatsApp twice is a typo, not two builds.
        """
        seen: list[str] = []
        for channel in self.channels:
            if channel not in seen:
                seen.append(channel)
        return tuple(sorted(seen, key=list(CHANNEL_ADD_MINOR).index))

    @property
    def extra_languages(self) -> int:
        """Languages beyond the first. One language is included in the base."""
        return max(0, len(set(self.languages)) - 1)


@dataclass(frozen=True)
class Quote:
    """A price and the whole reason for it."""

    product_type: str
    product_name: str
    currency: str
    billing_period: str
    line_items: tuple[LineItem, ...] = field(default=())
    monthly_conversation_limit: int = 0

    @property
    def subtotal_minor(self) -> int:
        """Everything except the discount line."""
        return sum(
            item.amount_minor
            for item in self.line_items
            if item.dimension != DIMENSION_DISCOUNT
        )

    @property
    def discount_minor(self) -> int:
        """Always returned positive, though it is stored as a negative line."""
        return -sum(
            item.amount_minor
            for item in self.line_items
            if item.dimension == DIMENSION_DISCOUNT
        )

    @property
    def total_minor(self) -> int:
        """The figure charged. A plain sum, so it cannot drift from the lines."""
        return sum(item.amount_minor for item in self.line_items)

    @property
    def display_total(self) -> str:
        return format_money(self.total_minor, self.currency)

    def to_plan(self, code: str = "custom") -> Plan:
        """The quote as something the sales engine can already quote and sell.

        Stage A made every price the agent says come from a ``Plan`` in a
        config. Returning one here means dynamic pricing needs no second path
        through the agent, the checkout or the order — a computed price is
        carried by the same object a fixed tier was.
        """
        return Plan(
            code=code,
            name=self.product_name,
            audience="",
            currency=self.currency,
            amount_minor=self.total_minor,
            billing_period=self.billing_period,
            seats=1,
            monthly_conversation_limit=self.monthly_conversation_limit,
            features=tuple(
                item.label
                for item in self.line_items
                if item.dimension not in (DIMENSION_BASE, DIMENSION_DISCOUNT)
            ),
            is_default=True,
        )


def _volume_line(monthly_conversations: int) -> tuple[LineItem | None, int]:
    """The band this volume falls in, and the limit that band buys.

    Bands rather than per-message pricing, so a buyer can tell what they will
    pay before they know their traffic.
    """
    for limit, amount_minor in VOLUME_BANDS:
        if monthly_conversations <= limit:
            if amount_minor == 0:
                return None, limit
            return (
                LineItem(
                    dimension=DIMENSION_VOLUME,
                    label=f"Up to {limit:,} conversations a month",
                    amount_minor=amount_minor,
                ),
                limit,
            )

    # Unreachable: Requirement rejects anything above the last band. Raising
    # rather than extrapolating keeps that true if a band is ever removed.
    raise PricingError(  # pragma: no cover - guarded by Requirement
        f"{monthly_conversations:,} conversations a month is beyond our bands."
    )


def price(requirement: Requirement) -> Quote:
    """Score a requirement into a quote.

    Deterministic: the same requirement always produces the same figure, and
    the figure is always the sum of lines a buyer can read back.
    """
    items: list[LineItem] = [
        LineItem(
            dimension=DIMENSION_BASE,
            label=PRODUCT_NAMES[requirement.product_type],
            amount_minor=PRODUCT_BASE_MINOR[requirement.product_type],
        )
    ]

    for channel in requirement.billable_channels:
        amount_minor = CHANNEL_ADD_MINOR[channel]
        if amount_minor == 0:
            # The web widget ships with every product. A zero line would read
            # as an upsell we are pretending to give away.
            continue
        items.append(
            LineItem(
                dimension=DIMENSION_CHANNEL,
                label=f"{CHANNEL_NAMES[channel]} channel",
                amount_minor=amount_minor,
            )
        )

    for integration in dict.fromkeys(requirement.integrations):
        items.append(
            LineItem(
                dimension=DIMENSION_INTEGRATION,
                label=f"{integration} integration",
                amount_minor=INTEGRATION_ADD_MINOR,
            )
        )

    if requirement.extra_languages:
        items.append(
            LineItem(
                dimension=DIMENSION_LANGUAGE,
                label=f"{requirement.extra_languages} extra language(s)",
                amount_minor=LANGUAGE_ADD_MINOR * requirement.extra_languages,
            )
        )

    volume_item, conversation_limit = _volume_line(requirement.monthly_conversations)
    if volume_item is not None:
        items.append(volume_item)

    if requirement.workflow_steps:
        items.append(
            LineItem(
                dimension=DIMENSION_WORKFLOW,
                label=f"{requirement.workflow_steps} custom workflow step(s)",
                amount_minor=WORKFLOW_STEP_ADD_MINOR * requirement.workflow_steps,
            )
        )

    if requirement.discount_percent:
        subtotal = sum(item.amount_minor for item in items)
        # Integer division, so the discount can never make the total a
        # fraction of a kobo, and rounds in the customer's favour by at most
        # one unit rather than ours.
        discount_minor = subtotal * requirement.discount_percent // 100
        items.append(
            LineItem(
                dimension=DIMENSION_DISCOUNT,
                label=f"{requirement.discount_percent}% discount",
                amount_minor=-discount_minor,
            )
        )

    return Quote(
        product_type=requirement.product_type,
        product_name=PRODUCT_NAMES[requirement.product_type],
        currency=CURRENCY_NGN,
        billing_period=BILLING_MONTH,
        line_items=tuple(items),
        monthly_conversation_limit=conversation_limit,
    )
