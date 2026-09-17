"""Quote an AI product from a requirement.

Public on purpose: a visitor deciding whether to buy needs a price before they
have an account, exactly as the storefront's fixed tiers were public. What is
*not* public is any way to influence the figure — the request carries a
requirement, never an amount, and the server computes the rest.

Nothing here charges. A quote is an answer to "what would this cost"; it is
stored so the checkout can find the requirement again, and the checkout re-runs
the pricing engine over that requirement rather than trusting the stored figure.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.pricing.complexity import (
    CHANNEL_ADD_MINOR,
    CHANNEL_NAMES,
    INTEGRATION_ADD_MINOR,
    INTEGRATION_LABELS,
    LANGUAGE_ADD_MINOR,
    PRODUCT_NAMES,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PricingError,
    price,
)
from app.pricing.quotes import QuoteError, QuoteService
from app.schemas.pricing import QuoteOut, RequirementIn

router = APIRouter(
    prefix="/pricing",
    tags=["Pricing"],
)


@router.get("/options")
def pricing_options():
    """What can be asked for. The front end builds its form from this.

    Publishing the dimensions rather than hardcoding them in the client means
    a channel we have not built cannot be offered by a stale page.

    Prices come from the pricing engine — one source of truth. Nothing here
    invents a figure the engine would disagree with.
    """
    base_prices = {
        PRODUCT_SALES_AGENT: 199_000_00,
        PRODUCT_SUPPORT_AGENT: 149_000_00,
        "workforce_agent": 348_000_00,
    }
    return {
        "products": [
            {
                "code": code,
                "name": name,
                "base_price_minor": base_prices.get(code, 0),
                "currency": "NGN",
            }
            for code, name in PRODUCT_NAMES.items()
        ],
        "channels": [
            {
                "code": code,
                "name": CHANNEL_NAMES[code],
                "included": CHANNEL_ADD_MINOR[code] == 0,
                "add_minor": CHANNEL_ADD_MINOR[code],
            }
            for code in CHANNEL_ADD_MINOR
        ],
        "integrations": [
            {
                "code": code,
                "name": INTEGRATION_LABELS.get(code, f"{code} integration"),
                "add_minor": INTEGRATION_ADD_MINOR,
            }
            for code in INTEGRATION_LABELS
        ],
        "languages": [
            {"code": "en", "name": "English", "included": True},
            {"code": "yo", "name": "Yoruba", "add_minor": LANGUAGE_ADD_MINOR},
            {"code": "ha", "name": "Hausa", "add_minor": LANGUAGE_ADD_MINOR},
            {"code": "ig", "name": "Igbo", "add_minor": LANGUAGE_ADD_MINOR},
        ],
    }


@router.post("/quote", response_model=QuoteOut)
def quote(payload: RequirementIn, db: Session = Depends(get_db)):
    """Price a requirement, with the breakdown that justifies the figure."""
    try:
        # Both steps: ``Requirement`` validates in its constructor, so an
        # unbuildable channel raises here rather than in ``price``.
        requirement = payload.to_requirement()
        computed = price(requirement)
    except PricingError as exc:
        # A requirement we will not quote for is a 400 with the reason, not a
        # guessed number. The message is written to be shown to the buyer.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Stored after pricing succeeds, so a reference always names something we
    # were willing to quote. ``issue`` prices it again rather than taking the
    # figure above — one function decides every amount in the system.
    stored = QuoteService(db).issue(requirement)

    return QuoteOut.from_quote(computed, reference=stored.reference)


@router.get("/quotes/{reference}", response_model=QuoteOut)
def get_quote(reference: str, db: Session = Depends(get_db)):
    """Read back a quote by reference, re-priced from its requirement.

    The chat widget needs this: the agent computes a figure mid-conversation and
    the buy panel has to show the buyer what they are about to pay for. Without
    it the panel would either show nothing or keep its own copy of the number,
    and a second copy of a price is a second chance to disagree with the
    charge.

    Unauthenticated, like the quote endpoint itself, and safe for the same
    reason: a reference is an unguessable name for a requirement *this server*
    priced. Reading one reveals what was quoted and nothing else, and it carries
    no authority over the amount — this route re-prices rather than reads, so a
    figure shown here is a figure the checkout would also compute.
    """
    try:
        _, computed = QuoteService(db).recompute(reference)
    except QuoteError as exc:
        # Unknown, unreadable and stale all land here. The message is written
        # to be shown to the buyer, and no case invents a replacement figure.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return QuoteOut.from_quote(computed, reference=reference)
