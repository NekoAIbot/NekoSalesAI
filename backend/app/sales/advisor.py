"""Which of the AIs we build does this business actually need."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.pricing.complexity import (
    PRODUCT_NAMES,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PRODUCT_WORKFORCE_AGENT,
)


@dataclass(frozen=True)
class ProductFit:
    product_type: str
    does: str
    because: str
    signals: tuple[str, ...] = ()


# Only the three purchasable products
FITS: dict[str, ProductFit] = {
    PRODUCT_SALES_AGENT: ProductFit(
        product_type=PRODUCT_SALES_AGENT,
        does="answers buyers, quotes your prices, takes payment and follows up",
        because="people ask what things cost and every one of those you miss is a sale someone else made",
        signals=(
            r"\bsell(s|ing)?\b",
            r"\bshop\b",
            r"\bstore\b",
            r"\bproducts?\b",
            r"\bprices?\b",
            r"\bpayments?\b",
            r"\border(s|ing)?\b",
            r"\bcustomers? (buy|order|pay)\b",
            r"\bleads?\b",
            r"\bsales\b",
            r"\brevenue\b",
        ),
    ),
    PRODUCT_SUPPORT_AGENT: ProductFit(
        product_type=PRODUCT_SUPPORT_AGENT,
        does="answers questions from your own material and hands anything commercial to you",
        because="the same questions arrive over and over, and answering them by hand is time you are not spending on the work itself",
        signals=(
            r"\bsupport\b",
            r"\bhelp ?desk\b",
            r"\bcustomer (care|service)\b",
            r"\bquestions?\b",
            r"\bfaqs?\b",
            r"\btickets?\b",
            r"\bissues?\b",
            r"\brefunds?\b",
            r"\bclients?\b",
            r"\bservice\b",
        ),
    ),
    PRODUCT_WORKFORCE_AGENT: ProductFit(
        product_type=PRODUCT_WORKFORCE_AGENT,
        does="combines sales and support into one coordinated AI team",
        because="your buyers need both answers and someone to close the sale, and having them share context means nothing falls through the cracks",
        signals=(
            r"\bboth\b",
            r"\ball\b",
            r"\bworkforce\b",
            r"\bsales \+ support\b",
            r"\bfull\b",
            r"\bcomplete\b",
            r"\bteam\b",
        ),
    ),
}


_ASKS_FOR_OPTIONS = re.compile(
    r"\b(what (do|can) you (build|make|do|offer)|what (are|is) (my |the )?"
    r"options?|which ones?|what have you got|show me|list them|everything)\b"
)

_DESCRIBES_A_BUSINESS = re.compile(
    r"\b(i|we) (run|own|have|manage|operate|started|do|sell|make|bake|repair|"
    r"rent|deliver|teach|train|supply)\b"
    r"|\b(i'?m|i am|we'?re|we are) (running|operating|managing|starting|"
    r"building|setting up|opening|selling|into)\b"
    r"|\b(my|our)(\s+\w+){0,2}\s+(business|company|shop|store|startup|brand|"
    r"firm|practice|agency|clinic|school|team|outfit|restaurant|salon|bakery|"
    r"boutique|pharmacy|hotel|garage|studio|cafe|kitchen|stall|academy|"
    r"workshop|dealership|gym|lounge|spa)\b"
    r"|\b(i'?m|i am|we'?re|we are) (a|an|the) \w+"
    r"|\bbusiness is\b|\bwe sell\b|\bi sell\b|\bwe deal in\b"
    r"|\b\w+\s+business\b"
    r"|\b\w+\s+store\b"
    r"|\b\w+\s+shop\b"
)

_WANTS_AN_OUTCOME = re.compile(
    r"\b(more|increase|increasing|grow|growing|boost|double|improve|drive)\s+"
    r"(my |our |the )?(customers?|clients?|sales|revenue|orders?|profits?|"
    r"bookings?|leads?|enquir\w+|inquir\w+|business|patrons?|traffic)\b"
    r"|\bprofits?\b|\bmake more money\b|\bgrow (my|our|the) business\b"
    r"|\bstop (losing|missing)\b|\bsave (me |us )?time\b"
    r"|\b(less|reduce|cut) (my |our )?(work|workload|admin|stress)\b"
    r"|\btoo many (messages|questions|enquir\w+|inquir\w+|calls?|chats?)\b"
)

_NAMES_A_NEED = re.compile(
    r"\b(i|we) (need|want|require|would like|'?m looking for|am looking for|"
    r"are looking for)\b[^.!?]{0,40}?"
    r"\b(a\.?i\.?|bots?|chat ?bots?|agents?|assistants?|automation|"
    r"systems?|software|tools?)\b"
)


def describes_a_business(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(
        _DESCRIBES_A_BUSINESS.search(lowered)
        or _WANTS_AN_OUTCOME.search(lowered)
        or _NAMES_A_NEED.search(lowered)
    )


def names_a_need(text: str) -> bool:
    return bool(_NAMES_A_NEED.search((text or "").lower()))


def product_names() -> tuple[str, ...]:
    return tuple(PRODUCT_NAMES[code] for code in FITS)


@dataclass(frozen=True)
class Recommendation:
    recommended: tuple[str, ...] = ()
    matched: tuple[str, ...] = ()
    too_vague: bool = False
    asked_for_options: bool = False
    unmet_need: bool = False

    @property
    def has_advice(self) -> bool:
        return bool(self.recommended)

    @property
    def needs_more_detail(self) -> bool:
        return self.too_vague


def recommend(description: str) -> Recommendation:
    """Recommend products based on a business description."""
    lowered = description.strip().lower()

    if _ASKS_FOR_OPTIONS.search(lowered):
        return Recommendation(
            recommended=tuple(FITS.keys()),
            matched=("showing all options",),
            asked_for_options=True,
        )

    if not describes_a_business(lowered):
        if len(lowered.split()) < 5:
            return Recommendation(too_vague=True)

    found: list[tuple[str, str]] = []
    for product_type, fit in FITS.items():
        for signal in fit.signals:
            match = re.search(signal, lowered)
            if match:
                found.append((product_type, match.group(0)))
                break

    if not found:
        if _NAMES_A_NEED.search(lowered):
            return Recommendation(unmet_need=True)
        if describes_a_business(lowered):
            return Recommendation(
                recommended=tuple(FITS.keys()),
                matched=("describes a business",),
            )
        return Recommendation(too_vague=True)

    seen = set()
    recommended = []
    matched = []
    for product_type, evidence in found:
        if product_type not in seen:
            seen.add(product_type)
            recommended.append(product_type)
            matched.append(evidence)

    return Recommendation(
        recommended=tuple(recommended),
        matched=tuple(matched),
    )


def describe_product(product_type: str) -> str:
    """Return a one-line description of a product for the buyer."""
    fit = FITS.get(product_type)
    if fit:
        return f"{PRODUCT_NAMES[product_type]} — {fit.does}"
    return PRODUCT_NAMES.get(product_type, product_type)


def advice_text(recommendation: Recommendation) -> str:
    """Format a recommendation into buyer-facing text."""
    if recommendation.too_vague:
        return (
            "Tell me a little about your business — what you sell, who you sell to, "
            "and what you'd rather not be doing by hand. Then I can point you at "
            "the right build."
        )

    if recommendation.asked_for_options:
        lines = ["Here's what Nera builds right now:"]
        for code in FITS:
            lines.append(f"• {describe_product(code)}")
        lines.append("\nTell me about your business and I'll say which one fits.")
        return "\n".join(lines)

    if recommendation.unmet_need:
        return (
            "That's not something Nera builds yet. I'll pass you to the team — "
            "they'll tell you plainly whether it's on the roadmap."
        )

    if not recommendation.recommended:
        return (
            "Tell me a bit more about what your business does and I'll say which "
            "build fits it."
        )

    lines = ["Here's what I'd build for that:"]
    for code in recommendation.recommended:
        fit = FITS[code]
        lines.append(f"• {PRODUCT_NAMES[code]} — {fit.does}")
    lines.append("\nShall I price one of these for you?")
    return "\n".join(lines)


def format_price(amount_minor: int) -> str:
    """Format minor units as Naira."""
    return f"₦{amount_minor / 100:,.0f}"
