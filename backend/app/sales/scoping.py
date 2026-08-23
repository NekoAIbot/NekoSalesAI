"""Asking a buyer what they need built, well enough to price it.

The complexity engine can price a build from a ``Requirement``. A buyer arrives
with a sentence. This module is the bridge, and it is deliberately the narrowest
possible one: four questions, each answer parsed into a bounded field, nothing
inferred.

**No prose becomes a number here.** Every parser either recognises an answer or
returns None, and None means the agent asks again rather than assumes. That is
the same rule ``app.products.interview`` follows for a customer's own price list,
and it exists for the same reason: the failure mode of a guess is not an awkward
sentence, it is a buyer being charged for a build nobody scoped.

**A scope is state the conversation carries, not state this module keeps.** The
caller hands in what has been collected so far and gets back a new ``Scope``, so
it can live in a database column, a chat transcript or a test fixture without
this module knowing which. Same shape as ``interested_plan_code``: passed into
``compose_reply``, handed back on the reply, persisted by the service.

Four questions rather than six. Languages and custom workflow steps are real
pricing dimensions, and the web configurator exposes both — but a chat that asks
six questions before naming a figure loses the buyer, so those two default to
none and the quote *says* they defaulted, with an offer to re-price. A default
stated out loud is honest; a default that silently shapes a price is not.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

from app.pricing.complexity import (
    CHANNEL_ADD_MINOR,
    CHANNEL_EMAIL,
    CHANNEL_NAMES,
    CHANNEL_TELEGRAM,
    CHANNEL_WEB,
    CHANNEL_WHATSAPP,
    MAX_INTEGRATIONS,
    MAX_QUOTABLE_CONVERSATIONS,
    PRODUCT_NAMES,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    VOLUME_BANDS,
    Requirement,
)

# The four things that have to be known before a build can be priced. Ordered:
# the product decides the base, the rest add to it.
STEP_PRODUCT = "products"
STEP_CHANNELS = "channels"
STEP_VOLUME = "monthly_conversations"
STEP_INTEGRATIONS = "integrations"

SCOPE_STEPS = (STEP_PRODUCT, STEP_CHANNELS, STEP_VOLUME, STEP_INTEGRATIONS)

# What ``product_type`` was called in scopes stored before a buyer could choose
# more than one. Read on the way in so a conversation that was mid-intake when
# this shipped does not lose its answer and start over.
LEGACY_STEP_PRODUCT = "product_type"


def product_options() -> str:
    """The catalog, as bullets, for the question that asks which to build.

    Generated rather than written out. Two products today, and the sentence that
    introduces them must not say "the two" — adding a third would otherwise mean
    finding every place a count was spelled into copy, and the one that got
    missed would be Nera telling a buyer there are two options while listing
    three.
    """
    return "\n".join(
        f"• {PRODUCT_NAMES[code]} — {_PRODUCT_BLURB[code]}"
        for code in PRODUCT_NAMES
    )


# What each product does, in one clause, for the question that offers them.
# Keyed by product type and checked against the catalog by the tests, so a
# product the engine can price always has something to say about itself.
_PRODUCT_BLURB: dict[str, str] = {
    PRODUCT_SALES_AGENT: (
        "answers buyers, quotes your prices, takes payment"
    ),
    PRODUCT_SUPPORT_AGENT: (
        "answers questions from your own material, hands anything commercial "
        "to you"
    ),
}


# What each step asks. Kept here rather than in the agent because a question and
# the parser for its answer have to change together — a reworded question that
# invites an answer the parser cannot read is a conversation that dead-ends.
QUESTIONS: dict[str, str] = {
    STEP_PRODUCT: (
        "Which of these do you need? You can have more than one — I price "
        "each separately so you can see what each is costing you.\n\n"
        f"{product_options()}"
    ),
    STEP_CHANNELS: (
        "Where should it answer? Any combination of: your website, Telegram, "
        "WhatsApp, email."
    ),
    STEP_VOLUME: (
        "Roughly how many conversations a month should it handle? A number is "
        "fine — say 500, 2,000, 10,000."
    ),
    STEP_INTEGRATIONS: (
        "Last one: how many of your systems does it need to talk to — CRM, "
        "calendar, helpdesk, stock? Say a number, or 'none'."
    ),
}


# Words a buyer uses for each product. Matched as whole words against the
# lowercased message, longest phrases first so "support agent" is not read as
# a request for an agent that does sales support.
#
# Every pattern is tried, not just the first that hits, because a buyer may want
# both: "I need the sales one and the support one" is one answer naming two
# products, and stopping at the first match would silently sell them half of
# what they asked for.
_PRODUCT_WORDS: tuple[tuple[str, str], ...] = (
    (r"\bsales (rep|representative|agent|person)\b", PRODUCT_SALES_AGENT),
    (r"\bsupport (agent|rep|representative|bot|desk)\b", PRODUCT_SUPPORT_AGENT),
    (r"\bcustomer (support|service|care)\b", PRODUCT_SUPPORT_AGENT),
    (r"\bhelp ?desk\b", PRODUCT_SUPPORT_AGENT),
    (r"\bsell(ing|er)?\b", PRODUCT_SALES_AGENT),
    (r"\bsales\b", PRODUCT_SALES_AGENT),
    (r"\bsupport\b", PRODUCT_SUPPORT_AGENT),
    (r"\bfirst (one|option)\b", PRODUCT_SALES_AGENT),
    (r"\bsecond (one|option)\b", PRODUCT_SUPPORT_AGENT),
)

# An explicit request for everything we build. "both" is here rather than in a
# two-product special case: it means "all of them" to a buyer looking at a list
# of two, and if the list ever grows the phrase stops matching what they can see
# — so it resolves to the whole catalog either way, which is what they asked for.
_ALL_PRODUCTS = re.compile(
    r"\b(both|all (of )?(them|it|these|those)?|everything|the (lot|whole lot)|"
    r"each|either)\b"
)

# "not the support one", "just sales, no support". A negation has to be found
# before the products are read, because "I don't need support" contains the word
# that would otherwise add a support agent to the order.
_NEGATED_PRODUCT = re.compile(
    r"\b(?:no|not|without|except|skip|drop|don'?t (?:need|want)|"
    r"nothing? (?:but|except))\s+(?:the\s+)?(\w+(?:\s+\w+)?)"
)

_CHANNEL_WORDS: tuple[tuple[str, str], ...] = (
    (r"\bweb ?site\b", CHANNEL_WEB),
    (r"\bweb\b", CHANNEL_WEB),
    (r"\bwidget\b", CHANNEL_WEB),
    (r"\bsite\b", CHANNEL_WEB),
    (r"\btele ?gram\b", CHANNEL_TELEGRAM),
    (r"\bwhats ?app\b", CHANNEL_WHATSAPP),
    (r"\bwa\b", CHANNEL_WHATSAPP),
    (r"\be ?mail\b", CHANNEL_EMAIL),
)

# "everywhere", "all of them" — an explicit request for the lot, which is a
# real answer and not a vague one.
_ALL_CHANNELS = re.compile(r"\b(everywhere|all of (them|it)|all four|all\b)")

_NONE_WORDS = re.compile(
    r"^\s*(none|no|nope|zero|0|nothing|n/a|na|not (yet|now)|just the (basics|basic))\s*[.!]?\s*$"
)

# A number, with or without thousands separators, and optionally scaled by k.
# "2,000" and "2k" are the same answer; "about 2k" parses too, because rounding
# a volume band is not the kind of guess this module refuses — the bands are
# themselves ranges, and the figure lands on a band boundary either way.
_NUMBER = re.compile(r"(\d[\d,]*)\s*(k\b|thousand\b)?", re.IGNORECASE)

# Words that mean "a lot" without naming a number. Deliberately unparsed: the
# volume bands are 500 to 50,000, and reading "loads" as any one of them would
# be inventing the buyer's traffic.
_VAGUE_VOLUME = re.compile(r"\b(lots?|loads|many|plenty|a few|some|busy|high)\b")


class ScopingError(ValueError):
    """An answer could not be read. Carries what to say back."""


@dataclass(frozen=True)
class Scope:
    """What is known so far about the build being priced.

    Every field is None until answered, so "not yet asked" and "answered as
    zero" are different states. Without that distinction a buyer who said "no
    integrations" would be asked again forever.
    """

    # One or more products. A buyer may want the sales agent, the support agent,
    # or both; each is priced separately on the same quote.
    products: tuple[str, ...] | None = None

    channels: tuple[str, ...] | None = None
    monthly_conversations: int | None = None
    integrations: int | None = None

    @property
    def product_type(self) -> str | None:
        """The first product chosen, for callers that deal in one.

        Read-only and derived, so it can never disagree with ``products``.
        """
        return self.products[0] if self.products else None

    # ---------- where the conversation is ----------

    @property
    def next_step(self) -> str | None:
        """The first thing still unknown, or None when it can be priced."""
        for step in SCOPE_STEPS:
            if getattr(self, step) is None:
                return step

        return None

    @property
    def is_complete(self) -> bool:
        return self.next_step is None

    @property
    def is_empty(self) -> bool:
        return all(getattr(self, step) is None for step in SCOPE_STEPS)

    def question(self) -> str | None:
        step = self.next_step

        return QUESTIONS[step] if step else None

    # ---------- becoming a price ----------

    def to_requirement(self) -> Requirement:
        """The priceable form. Raises if anything is still unknown.

        Languages and workflow steps are not asked conversationally and so are
        left at the engine's defaults — see this module's docstring for why, and
        ``app.sales.agent`` for the sentence that tells the buyer so.
        """
        if not self.is_complete:
            raise ScopingError(
                "This build has not been scoped enough to price yet."
            )

        return Requirement(
            products=self.products,
            channels=self.channels,
            integrations=tuple(f"system {n + 1}" for n in range(self.integrations)),
            monthly_conversations=self.monthly_conversations,
        )

    # ---------- storage ----------

    def to_json(self) -> str:
        return json.dumps(
            {
                STEP_PRODUCT: list(self.products) if self.products else None,
                STEP_CHANNELS: list(self.channels) if self.channels else None,
                STEP_VOLUME: self.monthly_conversations,
                STEP_INTEGRATIONS: self.integrations,
            }
        )

    @classmethod
    def from_json(cls, raw: str | None) -> "Scope":
        """Rebuild from a stored column. Junk reads as an empty scope.

        Never raises. A row that cannot be parsed means the buyer answers the
        four questions again, which is an annoyance; a raised exception here
        would mean a conversation that cannot be continued at all.
        """
        if not raw:
            return cls()

        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return cls()

        if not isinstance(data, dict):
            return cls()

        scope = cls()

        # A list now; a bare string in scopes stored before a buyer could pick
        # more than one. Both are read, so an in-flight conversation keeps the
        # answer it already gave rather than being asked again.
        products = data.get(STEP_PRODUCT)
        if isinstance(products, str):
            products = [products]
        if not products:
            legacy = data.get(LEGACY_STEP_PRODUCT)
            products = [legacy] if isinstance(legacy, str) else None

        if isinstance(products, list):
            known = tuple(
                code for code in PRODUCT_NAMES if code in set(products)
            )
            if known:
                scope = replace(scope, products=known)

        channels = data.get(STEP_CHANNELS)
        if isinstance(channels, list):
            known = tuple(c for c in channels if c in CHANNEL_ADD_MINOR)
            if known:
                scope = replace(scope, channels=known)

        volume = data.get(STEP_VOLUME)
        if isinstance(volume, int) and 0 < volume <= MAX_QUOTABLE_CONVERSATIONS:
            scope = replace(scope, monthly_conversations=volume)

        integrations = data.get(STEP_INTEGRATIONS)
        if isinstance(integrations, int) and 0 <= integrations <= MAX_INTEGRATIONS:
            scope = replace(scope, integrations=integrations)

        return scope


# ---------- reading one answer ----------


def parse_products(text: str) -> tuple[str, ...] | None:
    """Every product named in one answer, in catalog order.

    Returns None when nothing was recognised, which means ask again — not
    "they want nothing". A buyer who genuinely wants none of it stops replying
    or says so in words the agent's own rules handle; it is never inferred from
    an answer we could not read.
    """
    if _ALL_PRODUCTS.search(text):
        return tuple(PRODUCT_NAMES)

    # Cut the negated phrase out before reading products from what is left, so
    # "sales but not support" adds the sales agent only. Done by removal rather
    # than by subtracting a matched set, because the words inside a negation are
    # exactly the words that would otherwise be read as a request.
    remaining = _NEGATED_PRODUCT.sub(" ", text)

    found: list[str] = []
    for pattern, product in _PRODUCT_WORDS:
        if product in found:
            continue
        if re.search(pattern, remaining):
            found.append(product)

    if not found:
        return None

    return tuple(code for code in PRODUCT_NAMES if code in found)


def parse_product(text: str) -> str | None:
    """The single-product spelling, kept for callers that only want one.

    Returns the first product named, in catalog order.
    """
    products = parse_products(text)

    return products[0] if products else None


def parse_channels(text: str) -> tuple[str, ...] | None:
    if _ALL_CHANNELS.search(text):
        return tuple(CHANNEL_ADD_MINOR)

    found = []
    for pattern, channel in _CHANNEL_WORDS:
        if re.search(pattern, text) and channel not in found:
            found.append(channel)

    if not found:
        return None

    # The web widget ships with every build, so a buyer who named only Telegram
    # still gets it. Added silently because it is free and always present —
    # charging for it or hiding it would both be wrong.
    if CHANNEL_WEB not in found:
        found.append(CHANNEL_WEB)

    return tuple(found)


def parse_volume(text: str) -> int | None:
    """A monthly conversation count, snapped up to a band we have costed.

    Returns None for anything vague, and raises for a figure above the largest
    band — those are different outcomes. Vague means ask again; too large means
    a human has to scope it, and the agent must say so rather than quietly
    quoting the top band.
    """
    if _VAGUE_VOLUME.search(text) and not _NUMBER.search(text):
        return None

    match = _NUMBER.search(text)
    if not match:
        return None

    digits = match.group(1).replace(",", "")

    try:
        value = int(digits)
    except ValueError:
        return None

    if match.group(2):
        value *= 1_000

    if value <= 0:
        return None

    if value > MAX_QUOTABLE_CONVERSATIONS:
        raise ScopingError(
            f"Above {MAX_QUOTABLE_CONVERSATIONS:,} conversations a month I "
            "won't put a figure to it from here — that needs someone to scope "
            "properly. I've passed it on."
        )

    # Snap up to the band that covers it, so the figure quoted is one the engine
    # has actually costed rather than an interpolation between two of them.
    for band, _ in VOLUME_BANDS:
        if value <= band:
            return band

    return VOLUME_BANDS[-1][0]


def parse_integrations(text: str) -> int | None:
    if _NONE_WORDS.match(text):
        return 0

    match = _NUMBER.search(text)
    if not match:
        return None

    try:
        value = int(match.group(1).replace(",", ""))
    except ValueError:
        return None

    if match.group(2):
        value *= 1_000

    if value < 0:
        return None

    if value > MAX_INTEGRATIONS:
        raise ScopingError(
            f"More than {MAX_INTEGRATIONS} systems is a scoping job rather "
            "than a quote — I've passed it to the team so you get a real "
            "number rather than a guess."
        )

    return value


_PARSERS = {
    STEP_PRODUCT: parse_products,
    STEP_CHANNELS: parse_channels,
    STEP_VOLUME: parse_volume,
    STEP_INTEGRATIONS: parse_integrations,
}


def answer(scope: Scope, step: str, text: str) -> Scope | None:
    """Fold one answer into the scope, or return None if it was unreadable.

    None rather than an exception, because an unreadable answer is the common
    case and not an error: the buyer asked a question instead of answering one.
    The caller falls through to its other rules and re-asks afterwards.
    ``ScopingError`` is reserved for an answer that *was* understood and is
    outside what may be auto-quoted.
    """
    parser = _PARSERS.get(step)

    if parser is None:
        return None

    value = parser(text.lower().strip())

    if value is None:
        return None

    return replace(scope, **{step: value})


def product_name(product_type: str | None) -> str:
    return PRODUCT_NAMES.get(product_type or "", "the build")


def channel_names(channels: tuple[str, ...] | None) -> str:
    if not channels:
        return ""

    return ", ".join(CHANNEL_NAMES.get(c, c) for c in channels)
