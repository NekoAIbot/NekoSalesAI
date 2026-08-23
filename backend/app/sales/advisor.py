"""Which of the AIs we build does this business actually need.

A buyer does not arrive knowing they want a "sales agent with three channels and
a 2,000-conversation band". They arrive saying "I run a food store". The intake in
``app.sales.scoping`` is four good questions that all presuppose the buyer has
already chosen a product, and the first of them — "which of the two do you need?"
— asks someone who came for advice to give it instead.

So this module is the step before that: read what the business does, say which of
the products we build would help it and *why*, and let the buyer pick any number
of them. Then scoping takes over, unchanged.

Three rules, each of which exists because breaking it would be worse than having
no advisor at all.

**Nothing is recommended that is not in the catalog.** ``FITS`` is keyed by the
same product types ``app.pricing.complexity`` can price, and a test asserts the
two sets are equal — so a product added to the engine without being taught to the
advisor fails the suite, and a product described here that the engine cannot
price fails it too. There is no path by which Nera offers to build something that
does not exist.

**The count is never hardcoded.** Not in the copy, not in the parsing, not in the
selection. "Which of the two" appears nowhere in this module. Adding a third
product changes one dictionary and the questions grow a bullet on their own.
Everything downstream reads ``len(FITS)``.

**A need we cannot meet is named, not stretched.** A buyer who asks for an AI
that does their bookkeeping is told plainly that we do not build that, and shown
what we do build. The tempting alternative — reading "bookkeeping" as close enough
to "support" and quoting for it — is how a business ends up paying for software
that does not do the job it was bought for.

The matching is deliberately deterministic: regex over the description, no model
in the loop. That is not a placeholder for want of an LLM — rules cannot
hallucinate a fit or be talked into one, and a recommendation is the step that
decides what a buyer is about to be quoted for.

An LLM understanding layer is planned, and this module is shaped so it goes in
front rather than through. ``recommend`` is the seam: it takes free text and
returns a ``Recommendation`` — product types drawn from the catalog, plus the
evidence each was read from — and the agent acts only on that. Replacing its
internals with a model leaves the two guarantees intact, because neither of them
lives in the matching: the recommendation can only name products
``app.pricing.complexity`` can price, and nothing here decides an amount. Read a
buyer however well; the price is still computed by the engine from four bounded
answers. Anything added here should keep that boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.pricing.complexity import (
    PRODUCT_NAMES,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
)


@dataclass(frozen=True)
class ProductFit:
    """How one catalog product is described to someone choosing between them.

    Everything a buyer is told about *what to buy* comes from one of these, so a
    claim that is not true of the shipped product cannot be made by accident: it
    has to be written here, next to the product type it belongs to, where the
    test that checks this table against the pricing engine can see it.
    """

    product_type: str

    # One line, in the buyer's terms rather than ours. Shown when listing the
    # options and when explaining a recommendation.
    does: str

    # Why it fits a business like the one described. Completed as
    # "<name> — <because>", so it reads as a reason rather than a feature.
    because: str

    # What a buyer says that indicates this need. Whole-word patterns, matched
    # against the lowercased description. Deliberately about the *need*, not the
    # trade: "I take orders on WhatsApp" indicates selling whatever is sold.
    signals: tuple[str, ...] = ()


# Keyed by product type, and checked against the pricing engine by
# tests/test_advisor.py. Adding a product to PRODUCT_NAMES without adding it here
# is a test failure, which is the point: the Stage D pattern for a new product
# type is "price it, build it, provision it, and say who it is for".
FITS: dict[str, ProductFit] = {
    PRODUCT_SALES_AGENT: ProductFit(
        product_type=PRODUCT_SALES_AGENT,
        does=(
            "answers buyers, quotes your prices, takes payment and follows up"
        ),
        because=(
            "people ask what things cost and whether you have them, and every "
            "one of those you miss is a sale someone else made"
        ),
        signals=(
            r"\bsell(s|ing)?\b",
            r"\bshop\b",
            r"\bstore\b",
            r"\bstock\b",
            r"\bproducts?\b",
            r"\bprices?\b",
            r"\bpricing\b",
            r"\border(s|ing)?\b",
            r"\bcustomers? (buy|order|pay)\b",
            r"\bpayments?\b",
            r"\bcheckout\b",
            r"\bcatalogu?e\b",
            r"\bquote(s|d)?\b",
            r"\bleads?\b",
            r"\bboutique\b",
            r"\brestaurant\b",
            r"\bfood\b",
            r"\bpharmacy\b",
            r"\bsupermarket\b",
            r"\bmarket\b",
            r"\bvendor\b",
            r"\btrade\b",
            r"\bretail\b",
            r"\bwholesale\b",
            r"\bbookings?\b",
            r"\bappointments?\b",
            r"\breservations?\b",
            r"\bsales\b",
            r"\brevenue\b",
            r"\bconvert\b",
        ),
    ),
    PRODUCT_SUPPORT_AGENT: ProductFit(
        product_type=PRODUCT_SUPPORT_AGENT,
        does=(
            "answers questions from your own material and hands anything "
            "commercial straight to you"
        ),
        because=(
            "the same questions arrive over and over, and answering them by "
            "hand is time you are not spending on the work itself"
        ),
        signals=(
            r"\bsupport\b",
            r"\bhelp ?desk\b",
            r"\bcustomer (care|service)\b",
            r"\bcomplaints?\b",
            r"\bquestions?\b",
            r"\benquir(y|ies)\b",
            r"\binquir(y|ies)\b",
            r"\bfaqs?\b",
            r"\btickets?\b",
            r"\bissues?\b",
            r"\btroubleshoot(ing)?\b",
            r"\brefunds?\b",
            r"\breturns?\b",
            r"\bdelivery\b",
            r"\btracking\b",
            r"\bclients?\b",
            r"\bpatients?\b",
            r"\bstudents?\b",
            r"\bmembers?\b",
            r"\bschool\b",
            r"\bclinic\b",
            r"\bhospital\b",
            r"\bhotel\b",
            r"\bagency\b",
            r"\bservice\b",
            r"\bconsult(ing|ancy)\b",
            r"\bonboarding\b",
        ),
    ),
}


# A business described at all — as opposed to a greeting or a single word. Used
# to tell "I run a food store" from "hi", because advising on the strength of
# nothing is guessing dressed as consultancy.
_MIN_DESCRIPTION_WORDS = 3

# Phrases that mean "tell me what you have" rather than describing a business.
# These get the full list rather than a recommendation, which is the honest
# response to a question nobody has given us the information to answer.
_ASKS_FOR_OPTIONS = re.compile(
    r"\b(what (do|can) you (build|make|do|offer)|what (are|is) (my |the )?"
    r"options?|which ones?|what have you got|show me|list them|everything)\b"
)

# How someone says "this is my business". The advisor only offers an opinion
# when one of these is present or a need was actually named, because the
# alternative is answering questions nobody asked: "how much is it?" is three
# words with no product signal in them, and reading that as a business we cannot
# help would be a refusal invented out of a pricing question.
_DESCRIBES_A_BUSINESS = re.compile(
    r"\b(i|we) (run|own|have|manage|operate|started|do)\b"
    r"|\b(my|our) (business|company|shop|store|startup|brand|firm|practice|"
    r"agency|clinic|school|team|outfit)\b"
    r"|\b(i'?m|i am|we'?re|we are) (a|an|the) \w+"
    r"|\bbusiness is\b|\bwe sell\b|\bi sell\b|\bwe deal in\b"
)

# Someone naming what they want built, rather than what their business is.
#
# This gets the advisor's turn for the same reason a business description does,
# and the reason is the case we get wrong without it: "I need an AI that does my
# bookkeeping" is not a business description, so it used to fall through to the
# greeting — "tell me what your business needs done and I'll tell you what I'd
# build" — which reads as yes. A need we cannot meet has to meet the refusal,
# not an invitation.
#
# Narrowed by requiring the thing named to be a piece of software. "I need a
# quote" and "I need a discount" are not requests for advice about what to buy;
# they belong to the intake and the off-script guard respectively, and hijacking
# them would answer a question nobody asked.
_NAMES_A_NEED = re.compile(
    r"\b(i|we) (need|want|require|would like|'?m looking for|am looking for|"
    r"are looking for)\b[^.!?]{0,40}?"
    r"\b(a\.?i\.?|bots?|chat ?bots?|agents?|assistants?|automation|"
    r"systems?|software|tools?)\b"
)


def describes_a_business(text: str) -> bool:
    """Whether this message is someone telling us what they need.

    Either what the business does, or what they want built. Public because the
    agent has to decide whether the advisor gets the turn at all, and that
    decision belongs to the same module that knows what counts as a description.
    """
    lowered = (text or "").lower()

    return bool(
        _DESCRIBES_A_BUSINESS.search(lowered) or _NAMES_A_NEED.search(lowered)
    )


def product_names() -> tuple[str, ...]:
    """Every product's display name, in catalog order."""
    return tuple(PRODUCT_NAMES[code] for code in FITS)


@dataclass(frozen=True)
class Recommendation:
    """What was advised, and on what basis.

    ``recommended`` may be empty. That is a real outcome and the most important
    one to get right: it means the business was described clearly and none of the
    things we build address it. Saying so is the whole value of asking.
    """

    # The products worth buying for this business, catalog order.
    recommended: tuple[str, ...] = ()

    # What in the description each recommendation was read from, for the
    # reasoning trail. Parallel to ``recommended``.
    matched: tuple[str, ...] = ()

    # True when nothing was said that could be advised on — a greeting, a single
    # word. Different from an empty recommendation, which is an answer.
    too_vague: bool = False

    # True when the buyer asked what the options are rather than describing a
    # business. Also different: they get the list, not advice.
    asked_for_options: bool = False

    @property
    def has_advice(self) -> bool:
        return bool(self.recommended)

    @property
    def is_everything(self) -> bool:
        """Whether every product we build was recommended."""
        return len(self.recommended) == len(FITS)


def recommend(description: str) -> Recommendation:
    """Read a business description and say which products fit.

    Order follows the catalog rather than a score, deliberately. A ranking
    implies a confidence this matching does not have — it reads words, it does
    not understand a business — and a buyer who is shown two fits should choose
    between them on the reasons given, not on which one we listed first.
    """
    text = (description or "").lower().strip()

    if _ASKS_FOR_OPTIONS.search(text):
        return Recommendation(asked_for_options=True)

    if len(text.split()) < _MIN_DESCRIPTION_WORDS:
        return Recommendation(too_vague=True)

    recommended: list[str] = []
    matched: list[str] = []

    for code, fit in FITS.items():
        for pattern in fit.signals:
            found = re.search(pattern, text)
            if found:
                recommended.append(code)
                matched.append(found.group(0))
                break

    return Recommendation(
        recommended=tuple(recommended), matched=tuple(matched)
    )


# ---------- turning a recommendation into something to say ----------
#
# The copy lives here rather than in the agent for the same reason the scoping
# questions live beside their parsers: a sentence that offers a product and the
# table that says what that product does have to change together.


def _option_lines(codes: tuple[str, ...]) -> str:
    """One bullet per product, generated from the catalog."""
    return "\n".join(
        f"• {PRODUCT_NAMES[code]} — {FITS[code].does}" for code in codes
    )


def _reason_lines(recommendation: Recommendation) -> str:
    return "\n\n".join(
        f"**{PRODUCT_NAMES[code]}** — {FITS[code].because}."
        for code in recommendation.recommended
    )


def options_text() -> str:
    """Everything we build, when the buyer asked rather than described.

    Ends with what is *not* on the list. A buyer reading a short list can
    reasonably assume it is a sample of a larger catalogue, and letting them
    assume that is the same as claiming it.
    """
    return (
        "Here is everything I build today:\n\n"
        f"{_option_lines(tuple(FITS))}\n\n"
        "That is the whole list — I would rather tell you that than imply I "
        "can build anything you name. Which of them sounds like your problem? "
        "You can name more than one."
    )


def advice_text(recommendation: Recommendation) -> str:
    """What Nera says after reading a business description.

    Structure is the same in every case: what it read, what it would build, why,
    and one question. The question always allows *none of them*, because an
    advisor that cannot be told "neither" is a salesperson.

    None of this copy knows how many products there are. "Both of these" and
    "either one" read perfectly today and become quiet lies the moment a third
    product ships — the buyer is told there are two while looking at three. So
    the branch is on *one versus more than one*, which stays true at any size.
    """
    if recommendation.asked_for_options:
        return options_text()

    if recommendation.too_vague:
        return (
            "Tell me a bit more about what the business does and I'll say "
            "which of these would earn its keep:\n\n"
            f"{_option_lines(tuple(FITS))}"
        )

    if not recommendation.has_advice:
        # The case worth getting right. Nothing we build addresses what was
        # described, and the honest answer is short.
        return (
            "I'll be straight with you: from what you've described, I don't "
            "think what I build is the right fit — and I'd rather say so than "
            "sell you something that won't do the job.\n\n"
            f"{_option_lines(tuple(FITS))}\n\n"
            "If one of those is closer than I've read it, say so and I'll "
            "price it. Otherwise I'll pass you to someone who can talk about "
            "what else might help."
        )

    several = len(recommendation.recommended) > 1

    if several:
        lead = "Each of these would pull its weight, for a different reason:"
        closing = (
            "You can take any one of them on its own, or all of them together "
            "— I price each separately either way, so you can see what each "
            "one is costing you. Which do you want?"
        )
    else:
        lead = "Here's what I'd build for that:"
        closing = (
            "That's the one I'd start with. Say the word and I'll price it — "
            "four quick questions. If you'd rather see everything I build "
            "first, ask."
        )

    return f"{lead}\n\n{_reason_lines(recommendation)}\n\n{closing}"
