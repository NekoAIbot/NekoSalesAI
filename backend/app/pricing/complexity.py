"""Pricing an AI product from what it has to do, not from a fixed tier.

Two rules make this safe to put in front of a buyer.

**The price is computed, never accepted.** Nothing in this module reads an
amount from a caller. A requirement is scored into line items and the line
items are summed in integer minor units.

**Every figure is attributable.** A quote carries its line items, each naming
the dimension that produced it.

The currently purchasable catalog:
- AI Sales Agent (sales_agent)
- AI Support Agent (support_agent)
- Workforce (workforce_agent) — Sales + Support together

Future/unbuilt products are intentionally NOT purchasable and must not appear
in the builder as available options.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.products.config import Plan, format_money

CURRENCY_NGN = "NGN"

# Dimensions
DIMENSION_BASE = "base"
DIMENSION_CHANNEL = "channel"
DIMENSION_INTEGRATION = "integration"
DIMENSION_LANGUAGE = "language"
DIMENSION_VOLUME = "volume"
DIMENSION_DISCOUNT = "discount"
DIMENSION_BUNDLE = "bundle"

# Canonical product types - ONLY these are purchasable
PRODUCT_SALES_AGENT = "sales_agent"
PRODUCT_SUPPORT_AGENT = "support_agent"
PRODUCT_WORKFORCE_AGENT = "workforce_agent"

# Base prices in minor units (kobo)
PRODUCT_BASE_MINOR: dict[str, int] = {
    PRODUCT_SALES_AGENT: 199_000_00,
    PRODUCT_SUPPORT_AGENT: 149_000_00,
    PRODUCT_WORKFORCE_AGENT: 348_000_00,  # Sales + Support
}

# Customer-facing names
PRODUCT_NAMES: dict[str, str] = {
    PRODUCT_SALES_AGENT: "AI Sales Agent",
    PRODUCT_SUPPORT_AGENT: "AI Support Agent",
    PRODUCT_WORKFORCE_AGENT: "Workforce",
}

# Descriptions for the builder
PRODUCT_DESCRIPTIONS: dict[str, str] = {
    PRODUCT_SALES_AGENT: "Answers buyers, quotes your prices, takes payment, follows up",
    PRODUCT_SUPPORT_AGENT: "Answers questions from your knowledge base, escalates commercial queries",
    PRODUCT_WORKFORCE_AGENT: "Sales + Support operating as one team, shared context",
}

# Product order in UI
PRODUCT_ORDER: tuple[str, ...] = (
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PRODUCT_WORKFORCE_AGENT,
)

# Channels
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

# Integrations
INTEGRATION_ADD_MINOR = 2_000_00
MAX_INTEGRATIONS = 10

INTEGRATION_LABELS: dict[str, str] = {
    "crm": "CRM",
    "calendar": "Calendar",
    "payment": "Payment",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "ecommerce": "E-commerce",
    "pos": "Point of Sale",
    "helpdesk": "Helpdesk",
    "stock": "Stock Management",
    "erp": "ERP",
}


def _integration_label(integration: str, idx: int) -> str:
    """Human-readable label for an integration line item."""
    key = (integration or "").strip().lower().replace(" ", "_")
    if key in INTEGRATION_LABELS:
        return INTEGRATION_LABELS[key]
    if re.match(r"^(integration|system)_\d+$", key):
        return f"Integration {idx}"
    display = key.replace("_", " ")
    if display and display != key:
        return f"{display.title()}"
    return f"Integration {idx}"


# Languages
LANGUAGE_ADD_MINOR = 3_500_00
MAX_LANGUAGES = 6

# Canonical language catalog
LANGUAGES: dict[str, str] = {
    "en": "English",
    "yo": "Yoruba",
    "ha": "Hausa",
    "ig": "Igbo",
    "pid": "Nigerian Pidgin",
}


# Conversation volume
CONVERSATION_PRICE_MINOR = 5_00  # ₦5 = 500 kobo
MAX_QUOTABLE_CONVERSATIONS = 1_000_000

BILLING_MONTH = "month"


class PricingError(ValueError):
    """A requirement cannot be priced."""


@dataclass(frozen=True)
class LineItem:
    dimension: str
    label: str
    amount_minor: int

    @property
    def display_amount(self) -> str:
        return format_money(self.amount_minor, CURRENCY_NGN)


@dataclass(frozen=True)
class Requirement:
    product_type: str = PRODUCT_SALES_AGENT
    products: tuple[str, ...] = ()
    channels: tuple[str, ...] = (CHANNEL_WEB,)
    integrations: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    monthly_conversations: int = 500
    discount_percent: int = 0

    def __post_init__(self) -> None:
        asked = self.products or (self.product_type,)
        products = tuple(
            code for code in PRODUCT_ORDER if code in set(asked)
        )

        unknown = sorted(set(asked) - set(PRODUCT_ORDER))
        if unknown:
            raise PricingError(
                f"{unknown[0]!r} is not a product we currently offer."
            )

        if not products:
            raise PricingError("A build has to be for at least one product.")

        object.__setattr__(self, "products", products)
        object.__setattr__(self, "product_type", products[0])

        unknown = [c for c in self.channels if c not in CHANNEL_ADD_MINOR]
        if unknown:
            raise PricingError(
                f"We cannot answer on {', '.join(sorted(unknown))} yet."
            )

        if len(self.integrations) > MAX_INTEGRATIONS:
            raise PricingError(
                f"More than {MAX_INTEGRATIONS} integrations needs a human to scope it."
            )

        if len(self.languages) > MAX_LANGUAGES:
            raise PricingError(f"At most {MAX_LANGUAGES} languages per product.")

        if self.monthly_conversations < 0:
            raise PricingError("Conversation volume cannot be negative.")

        if self.monthly_conversations > MAX_QUOTABLE_CONVERSATIONS:
            raise PricingError(
                f"Above {MAX_QUOTABLE_CONVERSATIONS:,} conversations a month we price by hand."
            )

        if not 0 <= self.discount_percent <= 100:
            raise PricingError("A discount must be between 0 and 100 percent.")

    @property
    def billable_channels(self) -> tuple[str, ...]:
        seen: list[str] = []
        for channel in self.channels:
            if channel not in seen:
                seen.append(channel)
        return tuple(sorted(seen, key=list(CHANNEL_ADD_MINOR).index))

    @property
    def product_names(self) -> tuple[str, ...]:
        return tuple(PRODUCT_NAMES[code] for code in self.products)

    @property
    def extra_languages(self) -> int:
        return max(0, len(set(self.languages)) - 1)


@dataclass(frozen=True)
class Quote:
    product_type: str
    product_name: str
    currency: str
    billing_period: str
    line_items: tuple[LineItem, ...] = field(default=())
    monthly_conversation_limit: int = 0
    products: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.products:
            object.__setattr__(self, "products", (self.product_type,))

    @property
    def product_names(self) -> tuple[str, ...]:
        return tuple(PRODUCT_NAMES[code] for code in self.products)

    @property
    def is_bundle(self) -> bool:
        return len(self.products) > 1

    @property
    def subtotal_minor(self) -> int:
        return sum(
            item.amount_minor
            for item in self.line_items
            if item.dimension != DIMENSION_DISCOUNT
        )

    @property
    def discount_minor(self) -> int:
        return -sum(
            item.amount_minor
            for item in self.line_items
            if item.dimension == DIMENSION_DISCOUNT
        )

    @property
    def total_minor(self) -> int:
        return sum(item.amount_minor for item in self.line_items)

    @property
    def display_total(self) -> str:
        return format_money(self.total_minor, self.currency)

    def to_plan(self, code: str = "custom") -> Plan:
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
    if monthly_conversations <= 0:
        return None, 0

    amount_minor = monthly_conversations * CONVERSATION_PRICE_MINOR
    return (
        LineItem(
            dimension=DIMENSION_VOLUME,
            label=f"{monthly_conversations:,} conversations",
            amount_minor=amount_minor,
        ),
        monthly_conversations,
    )


def bundle_name(products: tuple[str, ...]) -> str:
    names = [PRODUCT_NAMES[code] for code in products]
    if len(names) == 1:
        return names[0]
    return f"{' + '.join(names[:-1])} + {names[-1]}"


def price(requirement: Requirement) -> Quote:
    items: list[LineItem] = [
        LineItem(
            dimension=DIMENSION_BASE,
            label=PRODUCT_NAMES[product],
            amount_minor=PRODUCT_BASE_MINOR[product],
        )
        for product in requirement.products
    ]

    for channel in requirement.billable_channels:
        amount_minor = CHANNEL_ADD_MINOR[channel]
        if amount_minor == 0:
            continue
        items.append(
            LineItem(
                dimension=DIMENSION_CHANNEL,
                label=f"{CHANNEL_NAMES[channel]} channel",
                amount_minor=amount_minor,
            )
        )

    for idx, integration in enumerate(dict.fromkeys(requirement.integrations), start=1):
        label = _integration_label(integration, idx)
        items.append(
            LineItem(
                dimension=DIMENSION_INTEGRATION,
                label=label,
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

    if requirement.discount_percent:
        subtotal = sum(item.amount_minor for item in items)
        discount_minor = subtotal * requirement.discount_percent // 100
        items.append(
            LineItem(
                dimension=DIMENSION_DISCOUNT,
                label=f"{requirement.discount_percent}% discount",
                amount_minor=-discount_minor,
            )
        )

    quote = Quote(
        product_type=requirement.product_type,
        product_name=bundle_name(requirement.products),
        products=requirement.products,
        currency=CURRENCY_NGN,
        billing_period=BILLING_MONTH,
        line_items=tuple(items),
        monthly_conversation_limit=conversation_limit,
    )

    return quote
