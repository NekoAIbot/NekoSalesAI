"""NekoSalesAI's own product configuration — the storefront.

**What Nera is.** Nera does not sell for a business. Nera *builds the AI that
does*. A business owner who wants an AI answering their buyers does not get
Nera; they get an AI sales representative that Nera made for them, with their
catalog, their prices and their name on it. Ask for an AI that handles support
and Nera builds that instead. Nera is the builder, not the worker — the one
thing it never is, is the AI doing your selling.

That distinction runs through every string in this file, and it is not
cosmetic. It decides what the agent claims when a visitor asks what it does,
what the landing page promises, and what a buyer thinks they are paying for. An
earlier version of this config described Nera as "an AI sales rep that answers
your buyers" — which described the *output* of the factory as though it were
the factory, and left a buyer expecting Nera itself to sit on their website.

This module used to *be* the engine's knowledge: module-level PLANS, FAQS and
CAPABILITIES that ``app.sales.agent`` read directly. It is now one instance of
``ProductConfig`` among many. The engine reads whichever config governs the
conversation in front of it; this is the one that governs conversations on
nekosales.ai, where the thing being sold is a build by Nera. The configs Nera
*produces* are rows, and they describe a worker rather than a builder.

That distinction is the point of Stage A. Before, a provisioned customer's
widget would have quoted these prices to their buyers, because the agent had
no other prices to reach for.

The rules that made this file trustworthy still hold:

1. Prices live in a config, never in a message. Every amount is an integer in
   the currency's minor unit (kobo for NGN) because binary floats cannot
   represent money exactly.
2. Every capability here carries a ``verified_by`` pointer to the code that
   implements it, and ``tests/test_catalog.py`` asserts those targets resolve,
   so a claim cannot outlive the feature it describes. This matters more for a
   builder than for a worker: "Nera builds whatever your business needs" is the
   most tempting sentence on the site and the easiest one to be lying with, so
   every claim about what it builds names the module that builds it.
3. Anything the config does not answer is off-script. The agent routes
   off-script terms to a human approval gate instead of inventing an answer.

Kept as plain Python rather than database rows: the storefront's prices should
be reviewable in a diff and impossible to change from inside a running
conversation. Customer configs are rows, because customers set their own.
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

# What Nera does, in the builder's voice. Only add a capability once the
# referenced code path actually ships — the catalog test fails if ``verified_by``
# does not resolve to a real module.
#
# Note what is *not* here: any claim that Nera answers your buyers. It does not.
# The AI it builds does. The first entry says so out loud, because a visitor who
# assumed otherwise would have bought the wrong thing.
CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        claim=(
            "Builds the AI your business needs and hands it over working — "
            "with your catalog, your prices and its own login. Nera is the "
            "builder; the AI it makes is what talks to your buyers."
        ),
        verified_by="app.payments.provisioning",
    ),
    Capability(
        claim=(
            "Prices a build from what it actually has to do — channels, "
            "traffic, systems to connect, languages, custom steps — and shows "
            "you every line that made up the figure."
        ),
        verified_by="app.pricing.complexity",
    ),
    Capability(
        claim=(
            "Refuses to quote something it cannot build. A product it can put "
            "a price on but not deliver stops the order rather than taking "
            "your money for it."
        ),
        verified_by="app.payments.provisioning",
    ),
    Capability(
        claim=(
            "Shows you why it answered the way it did — the signals it read "
            "and the rule it followed, on every single reply. So does every AI "
            "it builds."
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


# No fixed tiers. This used to be three of them — Founding User, Growth,
# Starter — and removing them is a deliberate pricing decision, not a cleanup.
#
# A tier is a bet that everyone at that size wants the same build. Nera does not
# sell a subscription to software that already exists; it is asked to build a
# specific AI, and what that costs depends on what the AI has to do: which
# product, which channels, how many systems it talks to, how much traffic it
# carries. Three cards on a page can only answer that by rounding, and rounding
# a price is either overcharging the small build or underpricing the large one.
#
# So every figure Nera quotes is now computed by ``app.pricing.complexity`` from
# a requirement the buyer stated, itemised so they can see what each line is
# for. ``STOREFRONT_CONFIG`` declares ``pricing_mode=PRICING_DYNAMIC`` below, and
# that is what routes a pricing question into the four scoping questions in
# ``app.sales.scoping`` instead of a price list.
#
# ``PLANS`` is gone rather than emptied, so nothing can quietly read a stale
# tier. Fixed plans remain a first-class feature of ``ProductConfig`` — a
# customer whose own product genuinely has three sizes still publishes them, and
# their agent still quotes them. What no longer exists is a fixed price for a
# *build*.
#
# Orders placed against the old codes keep working: an order freezes its plan
# name and amount at purchase, ``find_plan`` returns None for a retired code,
# and both ``app.followups.rules`` and ``app.payments.provisioning`` already fall
# back to what the order recorded.


FAQS: tuple[Faq, ...] = (
    Faq(
        question="Does Nera do the selling for me?",
        answer=(
            "No. Nera is the builder. It creates the AI that does the selling, "
            "and that AI is what sits on your site and answers your buyers — "
            "with your prices, your product and your name on it. Nera's job "
            "ends when the thing it built is working in your hands."
        ),
    ),
    Faq(
        question="What can Nera build?",
        answer=(
            "Today it builds and hands over two AI workers: an AI sales "
            "representative that answers buyers, quotes your published prices "
            "and takes payment, and an AI support agent that answers questions "
            "from your own material and escalates anything commercial. Ask for "
            "anything else and it says so and puts you in front of a human "
            "rather than pretending it can already ship it."
        ),
    ),
    Faq(
        question="How is a build priced?",
        answer=(
            "By what it has to do, not by a tier you have to fit into: which "
            "channels it answers on, how much traffic it handles, how many of "
            "your systems it has to talk to, how many languages, how many "
            "custom steps. You see every line that made up the figure before "
            "any card is involved."
        ),
    ),
    Faq(
        question="Can the AI make up a price or a discount?",
        answer=(
            "No — neither Nera nor anything it builds. Nera quotes only what "
            "the pricing engine computes, and the AI it builds you quotes only "
            "the prices you publish. Ask either for anything else and it says "
            "it needs to check with a human, and raises the request for "
            "someone to approve or decline."
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
            "No. Nera and everything it builds only answer people who come to "
            "you. Neither sends unsolicited messages."
        ),
    ),
)


# The agent may never agree to a discount on its own. Zero means every
# off-list term goes to the human approval gate, which is the point: a bug or
# a persuasive visitor must not be able to move the price.
MAX_AUTO_DISCOUNT_PERCENT = 0


STOREFRONT_CONFIG = ProductConfig(
    company_name="NekoSalesAI",
    # One sentence, and it has one job: say that Nera builds rather than sells.
    # This string is the first thing a buyer reads on the page and the first
    # thing Nera says in every greeting on every channel, so it is where the
    # misunderstanding either starts or is prevented.
    tagline="Nera builds the AI your business needs, and hands it over working.",
    description=(
        "Tell Nera what your business needs done. It tells you which AI would "
        "do it, prices the build line by line, and once you pay it builds the "
        "thing and hands it to you working. If you want an AI answering your "
        "buyers, Nera is not it — Nera is what makes it."
    ),
    support_email="hello@nekosales.ai",
    agent_name="Nera",
    # Nera is not a sales agent that happens to sell our software. It is the
    # builder: it sells the *making* of the other two roles and then provisions
    # them. Declaring that here is what lets the engine speak in the builder's
    # voice, and what stops anything ever provisioning a second factory —
    # ``PRODUCT_TYPE_TO_ROLE`` has no builder entry, so an order asking for one
    # fails loudly.
    role=ROLE_BUILDER,
    # First person, because this is what Nera says out loud on every channel.
    # The second paragraph exists to kill one specific misunderstanding before
    # it can cost someone money: a buyer who thinks Nera itself is what will
    # answer their customers has bought the wrong thing.
    agent_intro=(
        "and I build AI for businesses. Tell me what your business needs done "
        "and I'll tell you which AI does it, price the build line by line, and "
        "build it once you're happy with the number.\n\n"
        "I'm not the AI that will answer your buyers — I'm the one that makes "
        "it."
    ),
    opening_question="So: what does your business need?",
    # Priced by the engine, from what the buyer says the build has to do. There
    # is no plan list here on purpose — see the note above ``FAQS``.
    pricing_mode=PRICING_DYNAMIC,
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
    # The page calls the agent by the same name it introduces itself with. Read
    # from the config rather than typed into the template, so renaming it is one
    # edit and the greeting can never disagree with the button that opened it.
    "agent_name": STOREFRONT_CONFIG.agent_name,
}


def find_plan(code: str) -> Plan | None:
    """Look up a storefront plan by code.

    Returns None for everything now that the storefront publishes no tiers, and
    that is the point rather than an oversight: a retired code must resolve to
    nothing rather than to the nearest surviving plan. Callers that hold a code
    from an old order — ``app.followups.rules``, ``app.payments.provisioning`` —
    already fall back to the name and amount the order froze at purchase.

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
    "STOREFRONT_CONFIG",
    "Capability",
    "Faq",
    "Plan",
    "find_plan",
    "format_money",
    "plan_codes",
]
