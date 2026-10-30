"""Asking a buyer what they need built, well enough to price it.

The complexity engine can price a build from a ``Requirement``. A buyer arrives
with a sentence. This module is the bridge: four questions, each answer parsed
into a bounded field, nothing inferred.

**No prose becomes a number here.** Every parser either recognises an answer or
returns None.

**A scope is state the conversation carries, not state this module keeps.**

Three questions for Telegram (product, channels, volume, integrations).
Languages default to English in chat — can be re-priced if needed.
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
    INTEGRATION_LABELS,
    MAX_INTEGRATIONS,
    MAX_QUOTABLE_CONVERSATIONS,
    PRODUCT_NAMES,
    PRODUCT_ORDER,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PRODUCT_WORKFORCE_AGENT,
    PRODUCT_DESCRIPTIONS,
    Requirement,
    LANGUAGES,
)

# The four things that have to be known before a build can be priced. Ordered:
# the product decides the base, the rest add to it.
STEP_PRODUCT = "products"
STEP_CHANNELS = "channels"
STEP_VOLUME = "monthly_conversations"
STEP_INTEGRATIONS = "integrations"
STEP_LANGUAGES = "languages"

SCOPE_STEPS = (STEP_PRODUCT, STEP_CHANNELS, STEP_VOLUME, STEP_INTEGRATIONS, STEP_LANGUAGES)

# What ``product_type`` was called in scopes stored before a buyer could choose
# more than one. Read on the way in so a conversation that was mid-intake when
# this shipped does not lose its answer and start over.
LEGACY_STEP_PRODUCT = "product_type"


def product_options() -> str:
    """The catalog, as bullets, for the question that asks which to build."""
    return "\n".join(
        f"• {PRODUCT_NAMES[code]} — {PRODUCT_DESCRIPTIONS[code]}"
        for code in PRODUCT_ORDER
    )


def language_options() -> str:
    """The language catalog, as bullets, for Telegram selection."""
    return "\n".join(
        f"• {name}"
        for code, name in LANGUAGES.items()
    )


# What each step asks. Kept here rather than in the agent because a question and
# the parser for its answer have to change together.
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
    STEP_LANGUAGES: (
        "Which language(s) should your AI support? For example: English, Yoruba, Pidgin."
    ),
}

LANGUAGE_QUESTION = (
    "Which language(s) should your AI support?\n\n"
    f"{language_options()}\n\n"
    "Reply with the languages you want, e.g. 'English, Yoruba, Pidgin'."
)


# Words a buyer uses for each product. Matched as whole words against the
# lowercased message, longest phrases first so "support agent" is not read as
# a request for an agent that does sales support.
_PRODUCT_WORDS: tuple[tuple[str, str], ...] = (
    (r"\bsales (rep|representative|agent|person)\b", PRODUCT_SALES_AGENT),
    (r"\bsupport (agent|rep|representative|bot|desk)\b", PRODUCT_SUPPORT_AGENT),
    (r"\bcustomer (support|service|care)\b", PRODUCT_SUPPORT_AGENT),
    (r"\bhelp ?desk\b", PRODUCT_SUPPORT_AGENT),
    (r"\bworkforce\b", PRODUCT_WORKFORCE_AGENT),
    (r"\bworkforce (agent)?\b", PRODUCT_WORKFORCE_AGENT),
    (r"\bsales \+ support\b", PRODUCT_WORKFORCE_AGENT),
    (r"\bboth\b", PRODUCT_WORKFORCE_AGENT),
    (r"\ball\b", PRODUCT_WORKFORCE_AGENT),
    (r"\bsell(ing|er)?\b", PRODUCT_SALES_AGENT),
    (r"\bsales\b", PRODUCT_SALES_AGENT),
    (r"\bsupport\b", PRODUCT_SUPPORT_AGENT),
    (r"\bfirst (one|option)\b", PRODUCT_SALES_AGENT),
    (r"\bsecond (one|option)\b", PRODUCT_SUPPORT_AGENT),
)

# Words a buyer uses for languages
_LANGUAGE_WORDS: tuple[tuple[str, str], ...] = (
    (r"\beng(lish)?\b", "en"),
    (r"\byor(uba)?\b", "yo"),
    (r"\bau(s)?a\b", "ha"),  # Hausa variants
    (r"\bhaus(a)?\b", "ha"),
    (r"\bigb(o)?\b", "ig"),
    (r"\bpidgin\b", "pid"),
    (r"\bnigerian pidgin\b", "pid"),
)

# An explicit request for every product
_ALL_PRODUCTS = re.compile(
    r"\b(both|all (of )?(them|it|these|those)?|everything|the (lot|whole lot))\b"
)

# "not the support one", "just sales, no support"
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

_ALL_CHANNELS = re.compile(r"\b(everywhere|all of (them|it)|all four|all\b)")

_NONE_WORDS = re.compile(
    r"^\s*(none|no|nope|zero|0|nothing|nil|n/a|na|not (yet|now)|"
    r"just the (basics|basic))"
    r"(?:\s+(?:of (?:them|these|those|it)|at all|at the moment|for now|yet|"
    r"really|so far|right now|systems?|integrations?|apps?|tools?))*"
    r"\s*[.!]?\s*$"
)

_NUMBER = re.compile(r"(\d[\d,]*)\s*(k\b|thousand\b)?", re.IGNORECASE)

_WORD_COUNTS = {
    "zero": 0, "one": 1, "single": 1, "two": 2, "couple": 2, "both": 2,
    "pair": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
}

_WORD_COUNT = re.compile(
    r"\b(" + "|".join(sorted(_WORD_COUNTS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_WORD_SCALE = {"hundred": 100, "thousand": 1_000}

_WORD_VOLUME = re.compile(
    r"\b(?:((" + "|".join(_WORD_COUNTS) + r"|a)\s+)?(hundred|thousand))\b",
    re.IGNORECASE,
)


def parse_word_count(text: str) -> int | None:
    match = _WORD_COUNT.search(text or "")
    return _WORD_COUNTS[match.group(1).lower()] if match else None


def parse_word_volume(text: str) -> int | None:
    match = _WORD_VOLUME.search(text or "")
    if not match:
        return None
    # groups: 1=word count (e.g. "five"), 2=scale (e.g. "hundred")
    groups = match.groups()
    scale_word = groups[-1].lower() if groups[-1] else "hundred"
    multiplier = _WORD_SCALE.get(scale_word, 100)
    word_part = groups[0] if groups and groups[0] else None
    count = 1 if word_part is None else _WORD_COUNTS.get(word_part.lower().strip(), 1)
    return count * multiplier


_VAGUE_VOLUME = re.compile(r"\b(lots?|loads|many|plenty|a few|some|busy|high)\b")


class ScopingError(ValueError):
    """An answer could not be read."""


@dataclass(frozen=True)
class Scope:
    """What is known so far about the build being priced."""

    products: tuple[str, ...] | None = None
    channels: tuple[str, ...] | None = None
    monthly_conversations: int | None = None
    integrations: int | None = None
    languages: tuple[str, ...] | None = None
    recommended: tuple[str, ...] | None = None

    @property
    def product_type(self) -> str | None:
        return self.products[0] if self.products else None

    @property
    def next_step(self) -> str | None:
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

    def to_requirement(self) -> Requirement:
        if not self.is_complete:
            raise ScopingError("This build has not been scoped enough to price yet.")

        # A count is a count. The buyer said "15 integrations", not "CRM,
        # calendar, payment...". Inventing canonical names here put a
        # fabricated system list on the quote — the buyer was told they were
        # getting CRM when they had only said "15". Neutral slot labels keep
        # the count honest; the actual systems are identified at implementation.
        n = self.integrations or 0
        integrations = tuple(f"integration_slot_{i}" for i in range(1, n + 1))

        return Requirement(
            products=self.products,
            channels=self.channels,
            integrations=integrations,
            monthly_conversations=self.monthly_conversations or 500,
            languages=self.languages or ("en",),
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                STEP_PRODUCT: list(self.products) if self.products else None,
                STEP_CHANNELS: list(self.channels) if self.channels else None,
                STEP_VOLUME: self.monthly_conversations,
                STEP_INTEGRATIONS: self.integrations,
                STEP_LANGUAGES: list(self.languages) if self.languages else None,
                "recommended": list(self.recommended) if self.recommended else None,
            }
        )

    @classmethod
    def from_json(cls, raw: str | None) -> "Scope":
        if not raw:
            return cls()

        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return cls()

        if not isinstance(data, dict):
            return cls()

        scope = cls()

        products = data.get(STEP_PRODUCT)
        if isinstance(products, str):
            products = [products]
        if not products:
            legacy = data.get(LEGACY_STEP_PRODUCT)
            products = [legacy] if isinstance(legacy, str) else None

        if isinstance(products, list):
            known = tuple(code for code in PRODUCT_ORDER if code in set(products))
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

        languages = data.get(STEP_LANGUAGES)
        if isinstance(languages, list):
            scope = replace(scope, languages=tuple(languages))
        
        recommended = data.get("recommended")
        if isinstance(recommended, list):
            known = tuple(code for code in PRODUCT_ORDER if code in set(recommended))
            if known:
                scope = replace(scope, recommended=known)

        return scope


def parse_products(text: str) -> tuple[str, ...] | None:
    if _ALL_PRODUCTS.search(text):
        # "Both" / "all of it" means the complete capability set: selling and
        # answering. That is what Workforce *is* — the sales and support
        # agents as one team — not Workforce plus its two components, which
        # would charge the buyer twice for the same roles.
        return (PRODUCT_WORKFORCE_AGENT,)

    remaining = _NEGATED_PRODUCT.sub(" ", text)

    found: list[str] = []
    for pattern, product in _PRODUCT_WORDS:
        if product in found:
            continue
        if re.search(pattern, remaining):
            found.append(product)

    if not found:
        return None

    # A buyer naming both components has described Workforce; keep the
    # components as separate products only when they named exactly one.
    if PRODUCT_SALES_AGENT in found and PRODUCT_SUPPORT_AGENT in found:
        return (PRODUCT_WORKFORCE_AGENT,)

    return tuple(code for code in PRODUCT_ORDER if code in found)


def parse_product(text: str) -> str | None:
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

    if CHANNEL_WEB not in found:
        found.append(CHANNEL_WEB)

    return tuple(found)


def parse_languages(text: str) -> tuple[str, ...] | None:
    """Parse language selections from text. Returns tuple of language codes."""
    found = set()
    for pattern, code in _LANGUAGE_WORDS:
        if re.search(pattern, text.lower()):
            found.add(code)
    return tuple(found) if found else None


def parse_volume(text: str) -> int | None:
    if _VAGUE_VOLUME.search(text) and not _NUMBER.search(text):
        return None

    match = _NUMBER.search(text)
    if not match:
        spelled = parse_word_volume(text)
        if spelled is None:
            return None
        value = spelled
    else:
        digits = match.group(1).replace(",", "")
        try:
            value = int(digits)
        except ValueError:
            return None
        if match.group(2):
            value *= 1_000

    if value <= 0:
        return None

    # The exact figure the buyer gave. The pricing engine prices any volume
    # (₦5 per conversation), so snapping 12,000 up to a 25,000 band priced the
    # buyer for more than twice what they asked for. Bands are a UI hint for
    # the question text, not a rounding rule for the answer.
    if value > MAX_QUOTABLE_CONVERSATIONS:
        raise ScopingError(
            f"Above {MAX_QUOTABLE_CONVERSATIONS:,} conversations a month I "
            "won't put a figure to it from here — that needs someone to scope "
            "properly. I've passed it on."
        )

    return value


_ALL_WORDS = re.compile(
    r"^\s*(all(\s+of\s+(them|it|these|those))?|everything|every system|"
    r"the\s+(full\s+)?(lot|works))(\s+please)?\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def parse_integrations(text: str) -> int | None:
    if _NONE_WORDS.match(text):
        return 0

    if _ALL_WORDS.match(text.strip()):
        # "All of them" means every system in the catalog, priced as the full
        # set rather than left unanswered.
        return len(INTEGRATION_LABELS)

    match = _NUMBER.search(text)
    if not match:
        return parse_word_count(text)

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
    STEP_LANGUAGES: parse_languages,
}


_VOLUME_CONTEXT_RE = re.compile(
    r"(?:around|about|roughly|approx(?:imately)?|handle|get|receive|have)?\s*"
    r"(\d[\d,]*\s*(?:k\b|thousand\b)?)\s*"
    r"(?:conversations?|chats?|messages?|inquiries|enquiries|visitors?|leads?|a month|monthly|per month)",
    re.IGNORECASE,
)

_INTEGRATION_CONTEXT_RE = re.compile(
    r"\b(\d+)\s*(?:systems?|integrations?|apps?|tools?|software)\b",
    re.IGNORECASE,
)


def extract_natural_scope(
    scope: Scope,
    text: str,
    pending: str | None = None,
) -> tuple[Scope, list[str]]:
    """Extract any scope dimensions explicitly provided in a natural message.

    Extracts dimensions that are present without overwriting already-configured
    values. When extracting out of turn, requires explicit context (e.g. volume
    keywords like 'chats/conversations/a month') so unrelated numbers are not
    mistaken for volume.
    """
    extracted: list[str] = []
    lowered = (text or "").lower().strip()
    if not lowered:
        return scope, extracted

    # 1. Product
    if scope.products is None:
        if pending == STEP_PRODUCT:
            prods = parse_products(lowered)
            if prods:
                scope = replace(scope, products=prods)
                extracted.append("product")
        else:
            prods = parse_products(lowered)
            if prods:
                from app.sales.advisor import names_a_need

                if names_a_need(lowered):
                    scope = replace(scope, products=prods)
                    extracted.append("product")

    # 2. Channels
    if scope.channels is None:
        has_channel = _ALL_CHANNELS.search(lowered) or any(
            re.search(pat, lowered) for pat, _ in _CHANNEL_WORDS
        )
        if has_channel:
            chans = parse_channels(lowered)
            if chans:
                scope = replace(scope, channels=chans)
                extracted.append("channels")

    # 3. Volume
    if scope.monthly_conversations is None:
        if pending == STEP_VOLUME:
            vol = parse_volume(lowered)
            if vol:
                scope = replace(scope, monthly_conversations=vol)
                extracted.append("volume")
        else:
            m = _VOLUME_CONTEXT_RE.search(lowered)
            if m:
                vol = parse_volume(m.group(0))
                if vol:
                    scope = replace(scope, monthly_conversations=vol)
                    extracted.append("volume")

    # 4. Integrations
    if scope.integrations is None:
        if pending == STEP_INTEGRATIONS:
            ints = parse_integrations(lowered)
            if ints is not None:
                scope = replace(scope, integrations=ints)
                extracted.append("integrations")
        else:
            if re.search(r"\bno\s+(?:integrations?|systems?|tools?|apps?)\b", lowered) or re.search(r"\b0\s+(?:integrations?|systems?)\b", lowered):
                scope = replace(scope, integrations=0)
                extracted.append("integrations")
            else:
                m = _INTEGRATION_CONTEXT_RE.search(lowered)
                if m:
                    ints = parse_integrations(m.group(0))
                    if ints is not None:
                        scope = replace(scope, integrations=ints)
                        extracted.append("integrations")

    # 5. Languages
    if scope.languages is None:
        if pending == STEP_LANGUAGES:
            langs = parse_languages(lowered)
            if langs:
                scope = replace(scope, languages=langs)
                extracted.append("languages")
        else:
            has_lang = any(re.search(pat, lowered) for pat, _ in _LANGUAGE_WORDS)
            if has_lang:
                langs = parse_languages(lowered)
                if langs:
                    scope = replace(scope, languages=langs)
                    extracted.append("languages")

    return scope, extracted


def retain_scope_from_memory(scope: Scope, memory: Any) -> tuple[Scope, list[str]]:
    """Populate missing scope dimensions from facts retained across turns in memory."""
    retained: list[str] = []
    if memory is None:
        return scope, retained

    # Retain channels
    if scope.channels is None:
        ch_fact = memory.fact("business", "where_customers_reach_us")
        if ch_fact:
            chans = parse_channels(ch_fact)
            if chans:
                scope = replace(scope, channels=chans)
                retained.append("channels")

    # Retain volume
    if scope.monthly_conversations is None:
        vol_fact = memory.fact("business", "monthly_volume")
        if vol_fact:
            try:
                vol = int(vol_fact)
                if 0 < vol <= MAX_QUOTABLE_CONVERSATIONS:
                    scope = replace(scope, monthly_conversations=vol)
                    retained.append("volume")
            except (ValueError, TypeError):
                pass

    # Retain languages
    if scope.languages is None:
        lang_fact = memory.fact("requirements", "languages")
        if lang_fact:
            langs = parse_languages(lang_fact)
            if langs:
                scope = replace(scope, languages=langs)
                retained.append("languages")

    return scope, retained


def describe_extracted_lead_in(extracted: list[str], scope: Scope) -> str:
    """Create a conversational acknowledgment of what was extracted from the buyer's words."""
    if not extracted:
        return "Noted."

    parts = []
    if "product" in extracted and scope.products:
        p_names = [PRODUCT_NAMES.get(p, p) for p in scope.products]
        parts.append(f"the {' and '.join(p_names)}")
    if "channels" in extracted and scope.channels:
        c_names = channel_names(scope.channels)
        parts.append(f"for {c_names}")
    if "volume" in extracted and scope.monthly_conversations:
        parts.append(f"handling about {scope.monthly_conversations:,} conversations a month")
    if "integrations" in extracted and scope.integrations is not None:
        if scope.integrations == 0:
            parts.append("with no extra system integrations")
        else:
            parts.append(f"connected to {scope.integrations} system{'s' if scope.integrations != 1 else ''}")
    if "languages" in extracted and scope.languages:
        l_names = [LANGUAGES.get(l, l) for l in scope.languages]
        parts.append(f"supporting {', '.join(l_names)}")

    if not parts:
        return "Noted."

    return "Got it — " + ", ".join(parts) + "."


def answer(scope: Scope, step: str, text: str) -> Scope | None:
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
