"""Pricing an AI product from what it has to do.

See ``app.pricing.complexity`` for the design rules. The short version: a
price is computed from a bounded requirement, never read from a caller, and a
quote always equals the sum of the line items shown to the buyer.
"""

from app.pricing.complexity import (
    LineItem,
    PricingError,
    Quote,
    Requirement,
    price,
)

__all__ = ["LineItem", "PricingError", "Quote", "Requirement", "price"]
