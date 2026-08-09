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
    PRODUCT_NAMES,
    VOLUME_BANDS,
    PricingError,
    price,
)
from app.pricing.quotes import QuoteService
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
    """
    return {
        "products": [
            {"code": code, "name": name} for code, name in PRODUCT_NAMES.items()
        ],
        "channels": [
            {
                "code": code,
                "name": CHANNEL_NAMES[code],
                "included": CHANNEL_ADD_MINOR[code] == 0,
            }
            for code in CHANNEL_ADD_MINOR
        ],
        "volume_bands": [limit for limit, _ in VOLUME_BANDS],
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
