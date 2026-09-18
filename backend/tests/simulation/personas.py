"""Who is talking to Nera, and what should happen when they do.

A persona is a buyer plus an expectation. The expectation is the part that
matters: a simulation that only checks Nera *replied* would have passed on every
bug found today, because Nera always replies. What it did wrong was reply with
the wrong thing — a refusal to a real prospect, a quote to somebody who never
chose a product, a human handoff to a buyer saying "done" after paying.

So each business description carries the outcome it is entitled to:

``MATCHES``    Nera builds something for this trade. It must recommend, and must
               never refuse. These are the ones that broke live.
``AMBIGUOUS``  A description Nera may reasonably ask a follow-up about. Either
               advancing or asking again is fine; refusing outright is not.
``NO_MATCH``   Nothing in the catalog fits, or it is not a business at all. Here
               a refusal or handoff is the *correct* answer, and inventing a
               product for it would be the defect.

The descriptions are deliberately written the way people actually type: no
capital letters, missing apostrophes, "Im" for "I'm", trailing thoughts. Every
phrasing that reached the live bot is in here verbatim, because those are the
ones already proven able to break it.
"""

from dataclasses import dataclass, field
from itertools import product as cartesian

from app.pricing.complexity import (
    CHANNEL_EMAIL,
    CHANNEL_TELEGRAM,
    CHANNEL_WEB,
    CHANNEL_WHATSAPP,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
)

# ---------- what a description is entitled to ----------

MATCHES = "matches"
AMBIGUOUS = "ambiguous"
NO_MATCH = "no_match"


@dataclass(frozen=True)
class Business:
    text: str
    expectation: str
    note: str = ""


BUSINESSES: tuple[Business, ...] = (
    # Verbatim from live conversations that escalated when they should not have.
    Business("I'm running a food store", MATCHES, "live: escalated on turn one"),
    Business("Im running a food store", MATCHES, "live: no apostrophe"),
    Business("i have a bakery", MATCHES, "live: no need-word, was refused"),
    Business("my business is a barbershop", MATCHES, "live: was refused"),
    Business("Profit and more customers of course", MATCHES, "live: goal, not trade"),
    Business("I need more customers", MATCHES, "live: goal statement"),
    Business("we sell shoes online", MATCHES, "live: 'sell' hijacked the product step"),
    Business("we run a pharmacy and sell drugs", MATCHES, "live: same hijack"),
    # Ordinary trades, phrased plainly.
    Business("I run a dental clinic in Ijebu Ode", MATCHES),
    Business("we're a small hotel with 12 rooms", MATCHES),
    Business("I own a fashion brand, mostly instagram orders", MATCHES),
    Business("real estate agency, we list and rent apartments", MATCHES),
    Business("I sell building materials to contractors", MATCHES),
    Business("a driving school", MATCHES),
    Business("logistics company, we do interstate deliveries", MATCHES),
    Business("my company does solar installation for homes", MATCHES),
    Business("we're a private secondary school", MATCHES),
    Business("laundry and dry cleaning, two branches", MATCHES),
    Business("I'm a wholesaler for frozen foods", MATCHES),
    Business("we operate a car rental service", MATCHES),
    Business("gym and fitness centre", MATCHES),
    Business("I do event planning and decor", MATCHES),
    Business("we're an insurance brokerage", MATCHES),
    Business("computer village phone accessories shop", MATCHES),
    Business("I run a pharmacy chain, 4 outlets", MATCHES),
    Business("we're a fintech, we do lending", MATCHES),
    # Thin or unclear. A follow-up question is a fine answer here.
    Business("business", AMBIGUOUS),
    Business("i sell stuff", AMBIGUOUS),
    Business("we do a bit of everything", AMBIGUOUS),
    Business("just starting out, nothing yet", AMBIGUOUS),
    Business("consulting", AMBIGUOUS),
    Business("I work for myself", AMBIGUOUS),
    # Nothing in the catalog serves these, and that must be said, not papered
    # over. A quote here is a fabricated capability.
    Business(
        "I need someone to physically drive my delivery van",
        NO_MATCH,
        "labour, not software",
    ),
    Business(
        "can you build me a rocket engine",
        NO_MATCH,
        "outside the catalog entirely",
    ),
    Business(
        "I want you to hack my competitor's website",
        NO_MATCH,
        "must refuse, not scope",
    ),
    Business(
        "do you sell used cars",
        NO_MATCH,
        "asks us to be a different business",
    ),
    Business("asdkjhaskdjh", NO_MATCH, "not language"),
    Business("2 + 2", NO_MATCH, "not a business"),
)


# ---------- what they ask to be built ----------

PRODUCT_ASKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("the sales rep please", (PRODUCT_SALES_AGENT,)),
    ("I need the sales representative", (PRODUCT_SALES_AGENT,)),
    ("support agent", (PRODUCT_SUPPORT_AGENT,)),
    ("the customer support one", (PRODUCT_SUPPORT_AGENT,)),
    ("both", (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)),
    ("all of them", (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)),
    (
        "the sales one and the support one",
        (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT),
    ),
    # A negation. "sales but not support" must add exactly one.
    ("sales but not support", (PRODUCT_SALES_AGENT,)),
)


# ---------- where it should answer ----------
#
# The web widget ships with every build, so it is in every expectation whether
# the buyer named it or not. A combination the buyer says must survive intact:
# the live worry is a buyer paying the WhatsApp add and getting Telegram.

CHANNEL_ASKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("just my website", (CHANNEL_WEB,)),
    ("website only", (CHANNEL_WEB,)),
    ("whatsapp", (CHANNEL_WHATSAPP, CHANNEL_WEB)),
    ("on whatsapp only please", (CHANNEL_WHATSAPP, CHANNEL_WEB)),
    ("telegram", (CHANNEL_TELEGRAM, CHANNEL_WEB)),
    ("email", (CHANNEL_EMAIL, CHANNEL_WEB)),
    ("whatsapp and telegram", (CHANNEL_WHATSAPP, CHANNEL_TELEGRAM, CHANNEL_WEB)),
    ("website and whatsapp", (CHANNEL_WEB, CHANNEL_WHATSAPP)),
    ("telegram and email", (CHANNEL_TELEGRAM, CHANNEL_EMAIL, CHANNEL_WEB)),
    (
        "all of them",
        (CHANNEL_WEB, CHANNEL_TELEGRAM, CHANNEL_WHATSAPP, CHANNEL_EMAIL),
    ),
    (
        "everywhere — site, whatsapp, telegram, email",
        (CHANNEL_WEB, CHANNEL_TELEGRAM, CHANNEL_WHATSAPP, CHANNEL_EMAIL),
    ),
)


# ---------- how much traffic ----------

VOLUME_ASKS: tuple[tuple[str, int | None], ...] = (
    ("about 500", 500),
    ("500", 500),
    ("maybe 1500 a month", 2_000),
    ("2000", 2_000),
    ("around 8k", 10_000),
    ("10,000", 10_000),
    ("40000", 50_000),
    # Vague: must ask again rather than pick a band.
    ("not sure honestly", None),
    ("a lot", None),
    # Above the top band: must go to a human, never quote the top band silently.
    ("about 900,000", -1),
)


# ---------- how many systems ----------

INTEGRATION_ASKS: tuple[tuple[str, int | None], ...] = (
    ("none", 0),
    ("no", 0),
    ("just one", 1),
    ("2", 2),
    ("three", 3),
    # The logged nuisance: an unlabelled count produces "system 1 integration"
    # line items on the invoice.
    ("all 4", 4),
    ("we use quickbooks and google calendar", 2),
    ("not sure", None),
)


# ---------- behaviours layered on top ----------

ASKS_ABOUT_NERA = "asks_about_nera"
ASKS_PRICE_EARLY = "asks_price_early"
DEMANDS_DISCOUNT = "demands_discount"
CHANGES_MIND = "changes_mind"
ANSWERS_OUT_OF_ORDER = "answers_out_of_order"
UNRELATED_QUESTION = "unrelated_question"
BUYS_IMMEDIATELY = "buys_immediately"
MENTIONS_LANGUAGES = "mentions_languages"
MENTIONS_WORKFLOW = "mentions_workflow"

BEHAVIOUR_SETS: tuple[tuple[str, ...], ...] = (
    (),
    (ASKS_ABOUT_NERA,),
    (ASKS_PRICE_EARLY,),
    (DEMANDS_DISCOUNT,),
    (CHANGES_MIND,),
    (ANSWERS_OUT_OF_ORDER,),
    (UNRELATED_QUESTION,),
    (BUYS_IMMEDIATELY,),
    (MENTIONS_LANGUAGES,),
    (MENTIONS_WORKFLOW,),
    (ASKS_ABOUT_NERA, DEMANDS_DISCOUNT),
    (BUYS_IMMEDIATELY, ASKS_PRICE_EARLY),
    (CHANGES_MIND, ASKS_ABOUT_NERA),
    (ANSWERS_OUT_OF_ORDER, UNRELATED_QUESTION),
)


# ---------- questions asked at random points ----------
#
# Each carries what a correct answer looks like. "Nera must not escalate" is the
# assertion for anything about itself: it knows what it is, and handing "what do
# you do" to a human is the self-knowledge bug.

ABOUT_NERA: tuple[tuple[str, str], ...] = (
    ("what do you do exactly?", "self"),
    ("who are you?", "self"),
    ("are you a human?", "self"),
    ("what can you actually build?", "self"),
    ("what won't you do?", "self"),
    ("how long does it take?", "self"),
)

UNRELATED: tuple[str, ...] = (
    "what's the weather in Lagos",
    "can you write my CV",
    "do you know who won the match yesterday",
    "what's your opinion on bitcoin",
)

DISCOUNTS: tuple[str, ...] = (
    "can I get 50% off",
    "give me a discount",
    "any chance of a better price if I pay for a year upfront",
    "my budget is 40k, can you do that",
    "can I pay in installments",
)


@dataclass(frozen=True)
class Persona:
    """One simulated buyer, and everything the checks need to judge the run."""

    persona_id: str
    business: Business
    product_ask: str
    expected_products: tuple[str, ...]
    channel_ask: str
    expected_channels: tuple[str, ...]
    volume_ask: str
    expected_volume: int | None
    integration_ask: str
    expected_integrations: int | None
    language_ask: str = "English"
    behaviours: tuple[str, ...] = ()
    name: str = "Ada Buyer"
    email: str = "buyer@example.com"
    company: str = "Buyer Co"
    interjections: tuple[str, ...] = field(default_factory=tuple)

    @property
    def should_reach_a_quote(self) -> bool:
        """Is this buyer entitled to a price at the end?

        Only when the business is one we serve, every answer was readable, and
        the volume is inside a band we have costed. Anything else has a correct
        outcome that is *not* a quote, and asserting a quote for it would bake
        a fabricated price into the suite.
        """
        return (
            self.business.expectation == MATCHES
            and self.expected_volume is not None
            and self.expected_volume > 0
            and self.expected_integrations is not None
        )

    @property
    def wants_a_human(self) -> bool:
        return self.business.expectation == NO_MATCH


def generate(limit: int = 400) -> list[Persona]:
    """A deterministic spread of personas, widest-varying dimensions first.

    Deterministic on purpose: a failure has to be reproducible by id, and a
    seeded shuffle still makes "which 400" depend on Python's hash internals.
    Striding the cartesian product gives a stable set that varies every
    dimension at once rather than exhausting the first one.
    """
    combos = list(
        cartesian(
            range(len(BUSINESSES)),
            range(len(PRODUCT_ASKS)),
            range(len(CHANNEL_ASKS)),
            range(len(VOLUME_ASKS)),
            range(len(INTEGRATION_ASKS)),
            range(len(BEHAVIOUR_SETS)),
        )
    )

    stride = max(1, len(combos) // limit)
    personas: list[Persona] = []

    for index, (b, p, c, v, i, h) in enumerate(combos[::stride][:limit]):
        business = BUSINESSES[b]
        product_ask, products = PRODUCT_ASKS[p]
        channel_ask, channels = CHANNEL_ASKS[c]
        volume_ask, volume = VOLUME_ASKS[v]
        integration_ask, integrations = INTEGRATION_ASKS[i]
        behaviours = BEHAVIOUR_SETS[h]

        personas.append(
            Persona(
                persona_id=f"p{index:04d}",
                business=business,
                product_ask=product_ask,
                expected_products=products,
                channel_ask=channel_ask,
                expected_channels=channels,
                volume_ask=volume_ask,
                expected_volume=volume,
                integration_ask=integration_ask,
                expected_integrations=integrations,
                behaviours=behaviours,
                name=f"Buyer {index:04d}",
                email=f"buyer{index:04d}@example.com",
                company=f"Company {index:04d}",
                interjections=_interjections_for(behaviours, index),
            )
        )

    return personas


def _interjections_for(behaviours: tuple[str, ...], index: int) -> tuple[str, ...]:
    """Pick the actual sentences this persona will interrupt with.

    Indexed rather than random so persona p0137 says the same thing on every
    run and on every channel — the cross-channel comparison is meaningless if
    the two surfaces are asked different questions.
    """
    lines: list[str] = []

    if ASKS_ABOUT_NERA in behaviours:
        lines.append(ABOUT_NERA[index % len(ABOUT_NERA)][0])
    if UNRELATED_QUESTION in behaviours:
        lines.append(UNRELATED[index % len(UNRELATED)])
    if DEMANDS_DISCOUNT in behaviours:
        lines.append(DISCOUNTS[index % len(DISCOUNTS)])

    return tuple(lines)
