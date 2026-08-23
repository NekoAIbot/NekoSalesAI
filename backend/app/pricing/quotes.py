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
        # anything still reading the single-product field, including the
        # ``RequirementIn`` shape this JSON is documented as matching.
        "product_type": requirement.product_type,
        "products": list(requirement.products),
        "channels": list(requirement.channels),
        "integrations": list(requirement.integrations),
        "languages": list(requirement.languages),
        "monthly_conversations": requirement.monthly_conversations,
        "workflow_steps": requirement.workflow_steps,
        "discount_percent": requirement.discount_percent,
    }


def _requirement_from_dict(data: dict) -> Requirement:
    # A row written before quotes could cover more than one product has no
    # ``products`` key. Falling back to the single field means those quotes
    # re-price to exactly what they were sold at, rather than raising and
    # stranding a customer who already paid.
    products = data.get("products")
    product_type = data["product_type"]

    if products and product_type and product_type != products[0]:
        # We write both keys from one requirement, so they cannot disagree in a
        # row this code produced. A row where they do has been edited, and
        # picking a winner would mean charging for whichever product the reader
        # happened to prefer. Refusing is the only answer that cannot be wrong.
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
        workflow_steps=int(data.get("workflow_steps", 0)),
        discount_percent=int(data.get("discount_percent", 0)),
    )


def requirement_from_json(raw: str) -> Requirement:
    """The requirement a stored quote was priced from.

    Public because provisioning needs it: what a paid order entitles the buyer
    to is every product on the quote, and the quote row's ``product_type``
    column holds only the first of them. Reading the requirement is how
    "what did they pay for" gets answered from the same JSON the checkout
    re-priced, rather than from a summary column that cannot represent two.

    Raises rather than guessing — a requirement we cannot read is not one we
    can build.
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
            # The first product, for display and indexing. The authoritative
            # list is in requirement_json, which is also what the checkout
            # re-prices and what provisioning reads to decide what to build —
            # so this column being one of several is a summary, never a source.
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
        """Re-price a stored quote and check it still agrees with the row.

        The one place a stored quote turns back into a figure. Both redeeming it
        for payment and showing it back to the buyer come through here, so a
        price that would be refused at the checkout cannot be displayed as
        though it were still good.
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

        return quote, recomputed

    def redeem(self, reference: str) -> tuple[Quote, Plan]:
        """Re-price a stored quote and return the plan to charge.

        The price is recomputed rather than read. A quote reference names a
        requirement; it does not carry authority over the amount.
        """
        quote, recomputed = self.recompute(reference)

        return quote, recomputed.to_plan(code=plan_code_for(quote.reference))
