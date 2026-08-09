"""NekoSalesAI's own product configuration — the storefront.

This is one ``ProductConfig``, not the engine's only knowledge: it governs
conversations where the product being sold is NekoSalesAI itself. Customers
provisioned by the factory get their own. See ``app.catalog.products`` for the
rules, and ``app.products.config`` for the shape they share.
"""

from app.catalog.products import (
    CAPABILITIES,
    COMPANY,
    FAQS,
    MAX_AUTO_DISCOUNT_PERCENT,
    PLANS,
    STOREFRONT_CONFIG,
    Capability,
    Faq,
    Plan,
    find_plan,
    format_money,
    plan_codes,
)

__all__ = [
    "CAPABILITIES",
    "COMPANY",
    "FAQS",
    "MAX_AUTO_DISCOUNT_PERCENT",
    "PLANS",
    "STOREFRONT_CONFIG",
    "Capability",
    "Faq",
    "Plan",
    "find_plan",
    "format_money",
    "plan_codes",
]
