"""The published product catalog — the only claims the sales agent may make.

This module is deliberately plain Python data rather than database rows. The
sales agent quotes from it and from nothing else, so it needs to be
version-controlled, reviewable in a diff, and impossible to change from
inside a running conversation.

Three rules hold this together:

1. Prices live here only. Every amount is an integer in the currency's minor
   unit (kobo for NGN) because binary floats cannot represent money exactly.
2. Every capability carries a ``verified_by`` pointer to the code that
   implements it. ``tests/test_catalog.py`` asserts those targets resolve, so
   a claim cannot outlive the feature it describes.
3. Anything not written here is off-script. The agent routes off-script terms
   to a human approval gate instead of inventing an answer.
"""

from dataclasses import dataclass

COMPANY = {
    "name": "NekoSalesAI",
    "tagline": "An AI sales rep that answers your buyers in seconds.",
    "description": (
        "NekoSalesAI answers questions from people who land on your site, "
        "qualifies them, and hands you a deal you can close. It quotes only "
        "the prices and capabilities you publish, and asks you before "
        "agreeing to anything off your price list."
    ),
    "support_email": "hello@nekosales.ai",
}


@dataclass(frozen=True)
class Capability:
    """One thing the product does, and the code that proves it does it."""

    claim: str
    verified_by: str


# Only add a row here once the referenced code path actually ships. The
# catalog test fails if ``verified_by`` does not resolve to a real module.
CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        claim=(
            "Answers buyer questions in a live chat on your site using only "
            "the product and pricing information you publish."
        ),
        verified_by="app.sales.agent",
    ),
    Capability(
        claim=(
            "Shows you why it answered the way it did — the signals it read "
            "and the rule it followed, on every single reply."
        ),
        verified_by="app.sales.reasoning",
    ),
    Capability(
        claim=(
            "Asks for your approval before agreeing to any discount or term "
            "that is not on your published price list."
        ),
        verified_by="app.sales.approvals",
    ),
)


@dataclass(frozen=True)
class Plan:
    """A purchasable plan. ``amount_minor`` is in the minor currency unit."""

    code: str
    name: str
    audience: str
    currency: str
    amount_minor: int
    billing_period: str
    seats: int
    monthly_conversation_limit: int
    features: tuple[str, ...]
    is_default: bool = False

    @property
    def amount_major(self) -> float:
        """Display-only. Never use this for arithmetic or for Paystack."""
        return self.amount_minor / 100

    @property
    def display_price(self) -> str:
        return format_money(self.amount_minor, self.currency)


# Founder-set pricing. These are the numbers the agent will quote to real
# buyers, so they are the founder's call and not the engine's — change them
# here and every quote, payment link and page follows.
PLANS: tuple[Plan, ...] = (
    Plan(
        code="founding_annual",
        name="Founding User",
        audience="First 20 customers, paid annually up front.",
        currency="NGN",
        amount_minor=180_000_00,
        billing_period="year",
        seats=3,
        monthly_conversation_limit=2_000,
        features=(
            "Everything in Growth",
            "Locked-in founding price for as long as you stay subscribed",
            "Direct line to the founder for support",
            "Your feature requests get looked at first",
        ),
        is_default=True,
    ),
    Plan(
        code="growth_monthly",
        name="Growth",
        audience="Small teams handling steady inbound.",
        currency="NGN",
        amount_minor=25_000_00,
        billing_period="month",
        seats=3,
        monthly_conversation_limit=2_000,
        features=(
            "AI sales rep on your website",
            "Up to 2,000 buyer conversations a month",
            "3 team seats",
            "Approval gate for off-list discounts and terms",
            "Paystack checkout links",
            "Reasoning log on every AI reply",
        ),
    ),
    Plan(
        code="starter_monthly",
        name="Starter",
        audience="Solo founders testing inbound sales.",
        currency="NGN",
        amount_minor=9_000_00,
        billing_period="month",
        seats=1,
        monthly_conversation_limit=400,
        features=(
            "AI sales rep on your website",
            "Up to 400 buyer conversations a month",
            "1 seat",
            "Approval gate for off-list discounts and terms",
            "Reasoning log on every AI reply",
        ),
    ),
)

# The agent may never agree to a discount on its own. Zero means every
# off-list term goes to the human approval gate, which is the point: a bug or
# a persuasive visitor must not be able to move the price.
MAX_AUTO_DISCOUNT_PERCENT = 0


@dataclass(frozen=True)
class Faq:
    question: str
    answer: str


FAQS: tuple[Faq, ...] = (
    Faq(
        question="Can the AI make up a price or a discount?",
        answer=(
            "No. It can only quote the plans on this page. If you ask for "
            "anything else, it says it needs to check with the team and "
            "raises the request for a human to approve or decline."
        ),
    ),
    Faq(
        question="What happens if it does not know the answer?",
        answer=(
            "It tells you it does not know and passes the question to a "
            "human. It is built to say so rather than guess."
        ),
    ),
    Faq(
        question="Do you do cold outreach or scraped email lists?",
        answer=(
            "No. NekoSalesAI only answers people who come to you. It does "
            "not send unsolicited messages."
        ),
    ),
)


def format_money(amount_minor: int, currency: str) -> str:
    """Render minor units for display. Grouped, no trailing kobo when whole."""
    symbols = {"NGN": "₦", "USD": "$"}
    symbol = symbols.get(currency, f"{currency} ")

    if amount_minor % 100 == 0:
        return f"{symbol}{amount_minor // 100:,}"

    return f"{symbol}{amount_minor / 100:,.2f}"


def find_plan(code: str) -> Plan | None:
    """Look up a plan by code. Returns None rather than raising or guessing."""
    for plan in PLANS:
        if plan.code == code:
            return plan

    return None


def plan_codes() -> tuple[str, ...]:
    return tuple(plan.code for plan in PLANS)
