"""Issuing and redeeming quotes.

The security property this module exists for: **a quote reference is not a
price.** Redeeming a quote re-runs the pricing engine over the stored
requirement and charges that result. The stored total is compared against it
and a disagreement is refused.

That leaves exactly one way for a figure to reach Paystack: computed by
``app.pricing.complexity.price`` from a requirement this server validated.
"""

from __future__ import annotations

import json
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.models.quote import Quote
from app.pricing.complexity import PricingError, Requirement, price
from app.pricing.complexity import Quote as ComputedQuote
from app.products.config import Plan

logger = get_logger(__name__)

REFERENCE_PREFIX = "qt"
REFERENCE_BYTES = 12

# How a computed price is named everywhere a plan code is expected. One
# definition, because four layers read it: the agent's conversation remembers
# ``quote_<reference>`` in ``interested_plan_code``, the checkout unwraps it back
# to a reference, ``to_plan`` stamps it onto the order, and provisioning reads it
# to work out which product was bought.
QUOTE_PLAN_PREFIX = "quote_"


def plan_code_for(reference: str) -> str:
    return f"{QUOTE_PLAN_PREFIX}{reference}"


def reference_from_plan_code(code: str | None) -> str | None:
    """The quote reference inside a plan code, or None if it is not one."""
    if not code or not code.startswith(QUOTE_PLAN_PREFIX):
        return None

    return code[len(QUOTE_PLAN_PREFIX):] or None


class QuoteError(ValueError):
    """A quote cannot be issued or redeemed as asked."""


def build_reference() -> str:
    return f"{REFERENCE_PREFIX}_{secrets.token_hex(REFERENCE_BYTES)}"


def _requirement_to_dict(requirement: Requirement) -> dict:
    return {
        # Both spellings are written. ``products`` is what is read back;
        # ``product_type`` is kept so a row written now stays readable by
        # anything still reading the single-product field.
        "product_type": requirement.product_type,
        "products": list(requirement.products),
        "channels": list(requirement.channels),
        "integrations": list(requirement.integrations),
        "languages": list(requirement.languages),
        "monthly_conversations": requirement.monthly_conversations,
        "discount_percent": requirement.discount_percent,
    }


def _requirement_from_dict(data: dict) -> Requirement:
    """Rebuild a Requirement from stored JSON.

    Handles legacy data that may not have all fields.
    """
    products = data.get("products")
    product_type = data["product_type"]

    if products and product_type and product_type != products[0]:
        raise ValueError(
            f"Stored requirement disagrees with itself: product_type is "
            f"{product_type!r} but products begins {products[0]!r}."
        )

    return Requirement(
        product_type=product_type,
        products=tuple(products) if products else (),
        channels=tuple(data.get("channels", ())),
        integrations=tuple(data.get("integrations", ())),
        languages=tuple(data.get("languages", ())),
        monthly_conversations=int(data.get("monthly_conversations", 0)),
        discount_percent=int(data.get("discount_percent", 0)),
    )


def requirement_from_json(raw: str) -> Requirement:
    """The requirement a stored quote was priced from.

    Public because provisioning needs it.
    """
    return _requirement_from_dict(json.loads(raw))


class QuoteService:
    def __init__(self, db: Session):
        self.db = db

    def issue(
        self,
        requirement: Requirement,
        *,
        organization_id: int | None = None,
        conversation_id: int | None = None,
    ) -> Quote:
        """Price a requirement and store it so it can be bought later."""
        computed = price(requirement)

        quote = Quote(
            reference=build_reference(),
            organization_id=organization_id,
            conversation_id=conversation_id,
            requirement_json=json.dumps(_requirement_to_dict(requirement)),
            product_type=requirement.product_type,
            total_minor=computed.total_minor,
            currency=computed.currency,
        )

        self.db.add(quote)
        self.db.commit()
        self.db.refresh(quote)

        logger.info(
            "Quote %s issued: %s at %s",
            quote.reference,
            ", ".join(requirement.products),
            computed.display_total,
        )

        return quote

    def get(self, reference: str) -> Quote | None:
        return self.db.execute(
            select(Quote).where(Quote.reference == reference)
        ).scalars().first()

    def recompute(self, reference: str) -> tuple[Quote, ComputedQuote]:
        """Re-price a stored quote and check it still agrees with the row."""
        quote = self.get(reference)
        if quote is None:
            raise QuoteError(f"There is no quote with the reference {reference!r}.")

        try:
            requirement = _requirement_from_dict(json.loads(quote.requirement_json))
        except (ValueError, KeyError, TypeError) as exc:
            logger.error("Quote %s has an unreadable requirement", quote.reference)
            raise QuoteError(
                "We cannot re-price that quote. Please ask for a fresh one."
            ) from exc

        try:
            recomputed = price(requirement)
        except PricingError as exc:
            raise QuoteError(
                f"That quote is no longer valid: {exc}"
            ) from exc

        if recomputed.total_minor != quote.total_minor:
            logger.warning(
                "Quote %s no longer prices at its stored total (%s vs %s)",
                quote.reference,
                quote.total_minor,
                recomputed.total_minor,
            )
            raise QuoteError(
                "Our pricing has changed since that quote was made. "
                "Please ask for a fresh one."
            )

        return quote, recomputed

    def redeem(
        self,
        reference: str,
        *,
        requirement_override: Requirement | None = None,
    ) -> tuple[Quote, Plan]:
        """Re-price a stored quote and return the plan to charge."""
        quote = self.get(reference)
        if quote is None:
            raise QuoteError(f"There is no quote with the reference {reference!r}.")

        if requirement_override is not None:
            requirement = requirement_override
            quote.requirement_json = json.dumps(_requirement_to_dict(requirement))
            self.db.add(quote)
            self.db.commit()
        else:
            try:
                requirement = _requirement_from_dict(json.loads(quote.requirement_json))
            except (ValueError, KeyError, TypeError) as exc:
                logger.error("Quote %s has an unreadable requirement", quote.reference)
                raise QuoteError(
                    "We cannot re-price that quote. Please ask for a fresh one."
                ) from exc

        try:
            recomputed = price(requirement)
        except PricingError as exc:
            raise QuoteError(
                f"That quote is no longer valid: {exc}"
            ) from exc

        if recomputed.total_minor != quote.total_minor:
            logger.warning(
                "Quote %s no longer prices at its stored total (%s vs %s)",
                quote.reference,
                quote.total_minor,
                recomputed.total_minor,
            )
            raise QuoteError(
                "Our pricing has changed since that quote was made. "
                "Please ask for a fresh one."
            )

        quote.total_minor = recomputed.total_minor
        quote.currency = recomputed.currency
        self.db.add(quote)
        self.db.commit()

        return quote, recomputed.to_plan(code=plan_code_for(quote.reference))
