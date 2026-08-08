"""The published product catalog.

Everything the sales agent is permitted to say about price, capability or
commitment lives here. See ``app.catalog.products`` for the rules.
"""

from app.catalog.products import (
    CAPABILITIES,
    COMPANY,
    FAQS,
    MAX_AUTO_DISCOUNT_PERCENT,
    PLANS,
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
    "Capability",
    "Faq",
    "Plan",
    "find_plan",
    "format_money",
    "plan_codes",
]
