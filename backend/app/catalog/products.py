"""NekoSalesAI's own product configuration — the storefront.

This module used to *be* the engine's knowledge: module-level PLANS, FAQS and
CAPABILITIES that ``app.sales.agent`` read directly. It is now one instance of
``ProductConfig`` among many. The engine reads whichever config governs the
conversation in front of it; this is the one that governs conversations on
nekosales.ai, where the product being sold is NekoSalesAI itself.

That distinction is the point of Stage A. Before, a provisioned customer's
widget would have quoted these prices to their buyers, because the agent had
no other prices to reach for.

The rules that made this file trustworthy still hold:

1. Prices live in a config, never in a message. Every amount is an integer in
   the currency's minor unit (kobo for NGN) because binary floats cannot
   represent money exactly.
2. Every capability here carries a ``verified_by`` pointer to the code that
   implements it, and ``tests/test_catalog.py`` asserts those targets resolve,
   so a claim cannot outlive the feature it describes.
3. Anything the config does not answer is off-script. The agent routes
   off-script terms to a human approval gate instead of inventing an answer.

Kept as plain Python rather than database rows: the storefront's prices should
be reviewable in a diff and impossible to change from inside a running
conversation. Customer configs are rows, because customers set their own.
"""

from app.products.config import Capability, Faq, Plan, ProductConfig, format_money

# Only add a capability once the referenced code path actually ships. The
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


# The agent may never agree to a discount on its own. Zero means every
# off-list term goes to the human approval gate, which is the point: a bug or
# a persuasive visitor must not be able to move the price.
MAX_AUTO_DISCOUNT_PERCENT = 0


STOREFRONT_CONFIG = ProductConfig(
    company_name="NekoSalesAI",
    tagline="An AI sales rep that answers your buyers in seconds.",
    description=(
        "NekoSalesAI answers questions from people who land on your site, "
        "qualifies them, and hands you a deal you can close. It quotes only "
        "the prices and capabilities you publish, and asks you before "
        "agreeing to anything off your price list."
    ),
    support_email="hello@nekosales.ai",
    agent_name="the NekoSalesAI sales rep",
    plans=PLANS,
    capabilities=CAPABILITIES,
    faqs=FAQS,
    max_auto_discount_percent=MAX_AUTO_DISCOUNT_PERCENT,
)


# Kept as a dict because templates and the follow-up rules index it by key.
# Derived from the config rather than declared twice, so the landing page and
# the agent cannot drift apart.
COMPANY = {
    "name": STOREFRONT_CONFIG.company_name,
    "tagline": STOREFRONT_CONFIG.tagline,
    "description": STOREFRONT_CONFIG.description,
    "support_email": STOREFRONT_CONFIG.support_email,
}


def find_plan(code: str) -> Plan | None:
    """Look up a storefront plan by code.

    Storefront-scoped by definition. Code resolving a plan for an arbitrary
    conversation must use that conversation's config, not this — a customer's
    plan codes live in their own config and are not visible here.
    """
    return STOREFRONT_CONFIG.find_plan(code)


def plan_codes() -> tuple[str, ...]:
    return STOREFRONT_CONFIG.plan_codes


__all__ = [
    "CAPABILITIES",
    "COMPANY",
    "FAQS",
    "MAX_AUTO_DISCOUNT_PERCENT",
    "PLANS",
    "STOREFRONT_CONFIG",
    "Capability",
    "Faq",
    "Plan",
    "find_plan",
    "format_money",
    "plan_codes",
]
