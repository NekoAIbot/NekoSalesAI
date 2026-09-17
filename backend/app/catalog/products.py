"""NekoSalesAI's own product configuration — the storefront.

**What Nera is.** Nera does not sell for a business. Nera *builds the AI that
does*. A business owner who wants an AI answering their buyers does not get
Nera; they get an AI sales representative that Nera made for them.

**Current purchasable catalog:**
- AI Sales Agent
- AI Support Agent
- Workforce (Sales + Support operating together)

Future capabilities may be mentioned as "coming soon" but must not be offered
as purchasable options.
"""

from app.products.config import (
    PRICING_DYNAMIC,
    ROLE_BUILDER,
    Capability,
    Faq,
    Plan,
    ProductConfig,
    format_money,
)

# What Nera does, in the builder's voice.
CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        claim=(
            "Builds the AI your business needs and stays on to operate, monitor "
            "and improve it — with your catalog, your prices and its own login. "
            "Nera is the builder; the AI it makes is what talks to your buyers."
        ),
        verified_by="app.payments.provisioning",
    ),
    Capability(
        claim=(
            "Prices a build from what it actually has to do — channels, "
            "traffic, systems to connect, languages — and shows you every line "
            "that made up the figure."
        ),
        verified_by="app.pricing.complexity",
    ),
    Capability(
        claim=(
            "Refuses to quote something it cannot build AND keep running."
        ),
        verified_by="app.payments.provisioning",
    ),
    Capability(
        claim=(
            "Monitors the AI it built after launch — whether it is live, how it "
            "is performing, what is working and what is not."
        ),
        verified_by="app.followups.service",
    ),
    Capability(
        claim=(
            "Shows you why it answered the way it did — the signals it read "
            "and the rule it followed."
        ),
        verified_by="app.sales.reasoning",
    ),
    Capability(
        claim=(
            "Neither Nera nor anything it builds can invent a price or agree a "
            "discount. Off-list terms stop and wait for a human to approve."
        ),
        verified_by="app.sales.approvals",
    ),
)

FAQS: tuple[Faq, ...] = (
    Faq(
        question="Does Nera do the selling for me?",
        answer=(
            "No. Nera is the builder. It creates the AI that does the selling, "
            "and that AI is what sits on your site and answers your buyers — "
            "with your prices, your product and your name on it."
        ),
    ),
    Faq(
        question="What can Nera build?",
        answer=(
            "Today Nera builds three AI workers for your business: an AI Sales "
            "Agent that answers buyers, quotes your prices, takes payment and "
            "follows up; an AI Support Agent that answers questions from your own "
            "material; and Workforce, which combines both into one coordinated team. "
            "More capabilities are coming soon."
        ),
    ),
    Faq(
        question="How is a build priced?",
        answer=(
            "By what it has to do: which channels it answers on, how much traffic "
            "it handles, how many of your systems it has to talk to, and how many "
            "languages. You see every line that made up the figure before any card "
            "is involved."
        ),
    ),
    Faq(
        question="Can the AI make up a price or a discount?",
        answer=(
            "No — neither Nera nor anything it builds. Nera quotes only what "
            "the pricing engine computes."
        ),
    ),
    Faq(
        question="What happens after launch?",
        answer=(
            "Nera stays on. It monitors the AI it built and checks in regularly "
            "rather than waiting for you to report a problem."
        ),
    ),
    Faq(
        question="Do you do cold outreach or scraped email lists?",
        answer=(
            "No. Nera and everything it builds only answer people who come to you."
        ),
    ),
)

MAX_AUTO_DISCOUNT_PERCENT = 0

STOREFRONT_CONFIG = ProductConfig(
    company_name="NekoSalesAI",
    tagline="Nera builds the AI your business needs, and stays on to run it.",
    description=(
        "Tell Nera what your business needs done. It tells you which AI would "
        "do it, prices the build line by line, and once you pay it builds the "
        "thing and stays on to operate, monitor and improve it."
    ),
    support_email="hello@nekosales.ai",
    agent_name="Nera",
    role=ROLE_BUILDER,
    agent_intro=(
        "and I build AI for businesses. Tell me what your business needs done "
        "and I'll tell you which AI does it, price the build line by line, and "
        "build it once you're happy with the number.\n\n"
        "I'm not the AI that will answer your buyers — I'm the one that makes it."
    ),
    opening_question="So: what does your business need?",
    pricing_mode=PRICING_DYNAMIC,
    capabilities=CAPABILITIES,
    faqs=FAQS,
    max_auto_discount_percent=MAX_AUTO_DISCOUNT_PERCENT,
)

COMPANY = {
    "name": STOREFRONT_CONFIG.company_name,
    "tagline": STOREFRONT_CONFIG.tagline,
    "description": STOREFRONT_CONFIG.description,
    "support_email": STOREFRONT_CONFIG.support_email,
    "agent_name": STOREFRONT_CONFIG.agent_name,
}


def find_plan(code: str) -> Plan | None:
    return STOREFRONT_CONFIG.find_plan(code)


def plan_codes() -> tuple[str, ...]:
    return STOREFRONT_CONFIG.plan_codes


__all__ = [
    "CAPABILITIES",
    "COMPANY",
    "FAQS",
    "MAX_AUTO_DISCOUNT_PERCENT",
    "STOREFRONT_CONFIG",
    "Capability",
    "Faq",
    "Plan",
    "find_plan",
    "format_money",
    "plan_codes",
]
