"""Issuing and redeeming quotes.

The security property this module exists for: **a quote reference is not a
price.** Redeeming a quote re-runs the pricing engine over the stored
requirement and charges that result. The stored total is compared against it
and a disagreement is refused, so editing ``quotes.total_minor`` in the
database buys nothing — the row is evidence, not authority.

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
from app.products.config import Plan

logger = get_logger(__name__)

REFERENCE_PREFIX = "qt"
REFERENCE_BYTES = 12


class QuoteError(ValueError):
    """A quote cannot be issued or redeemed as asked."""


def build_reference() -> str:
    return f"{REFERENCE_PREFIX}_{secrets.token_hex(REFERENCE_BYTES)}"


def _requirement_to_dict(requirement: Requirement) -> dict:
    return {
        "product_type": requirement.product_type,
        "channels": list(requirement.channels),
        "integrations": list(requirement.integrations),
        "languages": list(requirement.languages),
        "monthly_conversations": requirement.monthly_conversations,
        "workflow_steps": requirement.workflow_steps,
        "discount_percent": requirement.discount_percent,
    }


def _requirement_from_dict(data: dict) -> Requirement:
    return Requirement(
        product_type=data["product_type"],
        channels=tuple(data.get("channels", ())),
        integrations=tuple(data.get("integrations", ())),
        languages=tuple(data.get("languages", ())),
        monthly_conversations=int(data.get("monthly_conversations", 0)),
        workflow_steps=int(data.get("workflow_steps", 0)),
        discount_percent=int(data.get("discount_percent", 0)),
    )


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
            requirement.product_type,
            computed.display_total,
        )

        return quote

    def get(self, reference: str) -> Quote | None:
        return self.db.execute(
            select(Quote).where(Quote.reference == reference)
        ).scalars().first()

    def redeem(self, reference: str) -> tuple[Quote, Plan]:
        """Re-price a stored quote and return the plan to charge.

        The price is recomputed rather than read. A quote reference names a
        requirement; it does not carry authority over the amount.
        """
        quote = self.get(reference)
        if quote is None:
            raise QuoteError(f"There is no quote with the reference {reference!r}.")

        try:
            requirement = _requirement_from_dict(json.loads(quote.requirement_json))
        except (ValueError, KeyError, TypeError) as exc:
            # A stored requirement we cannot read is not something to guess at.
            logger.error("Quote %s has an unreadable requirement", quote.reference)
            raise QuoteError(
                "We cannot re-price that quote. Please ask for a fresh one."
            ) from exc

        try:
            recomputed = price(requirement)
        except PricingError as exc:
            # The pricing rules changed and this requirement is no longer one
            # we quote for. Refusing is right: the alternative is charging for
            # something we have stopped agreeing to build.
            raise QuoteError(
                f"That quote is no longer valid: {exc}"
            ) from exc

        if recomputed.total_minor != quote.total_minor:
            # Either our prices moved or the row was edited. Both mean the
            # figure the buyer was shown is not the figure we would compute,
            # and charging either one silently would be wrong.
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

        return quote, recomputed.to_plan(code=f"quote_{quote.reference}")
