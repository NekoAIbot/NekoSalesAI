"""Rephrasing what the rule engine already decided to say.

Nera's replies are composed by ``app.sales.agent`` from rules: no model chooses
a price, a product or a commitment. That is deliberate and it is not changing.
What it costs is fluency — deterministic copy reads like deterministic copy, and
a buyer can tell.

So this module does one thing: take a reply the engine has already produced and
say the same thing better. Every fact in it is checked to survive, in both
directions, and any failure ships the deterministic text unchanged. There is no
path by which a model's output reaches a buyer without passing that check.

**What "in both directions" means, and why it is the whole design.** The obvious
check is that the original's facts are still present. That alone is not enough: a
candidate reading "the AI Sales Representative is ₦31,000, or ₦20,000 this week"
preserves every original fact and invents a price we never authorised. So the
verifier requires *equality* of the fact sets — nothing lost, and nothing gained.
Numbers, amounts, product names, quote references, emails and links are all
compared as multisets.

**Commitments cannot be introduced.** A vocabulary of obligation and absolutes —
"guarantee", "free", "refund", "unlimited", "anything", "24/7" — may appear in a
rephrasing only if it appeared in the original. This is what stops the failure
that fact-checking cannot see: "answers questions from your own material" turned
into "handles anything your customers need", which contains no number and no new
product name and is a capability claim we would have to honour. Capability
inflation nearly always arrives as an absolute, which is why the absolutes are
the guard.

**Honest limits.** This verifier is mechanical. It cannot catch a candidate that
is fluent, fact-preserving, absolute-free and still subtly wrong in emphasis, and
it is not a substitute for the copy being right before it gets here. What it
guarantees is narrower and worth stating exactly: no figure, product, reference
or commitment a buyer sees was written by a model. Everything else is tone.

Off by default. No ``GROQ_API_KEY`` means every call returns its input, so a
deployment that has not opted in behaves exactly as it did before this module
existed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config.logging import get_logger
from app.config.settings import settings
from app.pricing.complexity import PRODUCT_NAMES

logger = get_logger(__name__)


# ---------- the facts a rephrasing may not touch ----------

# Currency amounts as ``format_money`` renders them: a symbol, then grouped
# digits, optionally with kobo. Matched before bare numbers so "₦31,000" is one
# fact rather than two.
_MONEY = re.compile(r"[₦$]\s?\d[\d,]*(?:\.\d{2})?|(?:NGN|USD)\s?\d[\d,]*(?:\.\d{2})?")

# Every remaining run of digits — conversation volumes, integration counts,
# percentages, step counts. Commas stripped so "2,000" and "2000" compare equal;
# a model reformatting a number has not changed it.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Quote references, plan codes, widget tokens: anything the buyer might be asked
# to quote back to us. Getting one character wrong makes it unusable, and a
# buyer holding a reference nobody can find is worse than one holding none.
_REFERENCE = re.compile(r"\b(?:qt|quote)_[A-Za-z0-9]+\b")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_LINK = re.compile(r"https?://\S+")

# Words that create an obligation or make an absolute claim. A rephrasing may
# keep any of these it was given and may not introduce one it was not.
#
# The list is deliberately broad. A false rejection costs a deployment nothing —
# the deterministic text ships, which is what would have shipped anyway — while a
# false acceptance is a promise a business has to honour.
_COMMITMENTS = re.compile(
    r"\b(guarantee[ds]?|guaranteeing|promise[ds]?|assure[ds]?|ensure[ds]?|"
    r"free|discount(s|ed)?|refund(s|ed|able)?|waive[ds]?|"
    r"unlimited|any ?time|24/7|always|never|instant(ly)?|immediate(ly)?|"
    r"anything|everything|any need|all your|every ?thing|"
    r"fully|completely|entirely|totally|seamless(ly)?|end.to.end|"
    r"custom(ise|ize|ised|ized|isation|ization)?|bespoke|tailor(s|ed|ing)?|"
    r"risk.free|no.obligation|"
    r"cheapest|best price|lowest|beat any)\b"
)

# A model answering the instruction instead of following it: "Here is the
# rewritten version:", "Sure! ...". These preserve every fact and would ship a
# stage direction to a buyer, so they are rejected rather than trimmed — trimming
# guesses at where the preamble ends.
_META_PREAMBLE = re.compile(
    r"^\s*(sure|certainly|of course|here(?:'s| is| are)|rewritten|revised|"
    r"rephrased|version|option \d)\b[^\n]{0,60}[:\n]",
    re.IGNORECASE,
)

# A candidate this much longer than the original is not a rephrasing, and this
# much shorter has dropped something the fact checks do not cover.
_MAX_LENGTH_RATIO = 1.7
_MIN_LENGTH_RATIO = 0.45


def _multiset(pattern: re.Pattern[str], text: str) -> tuple[str, ...]:
    """Every match, normalised and sorted, so order and spacing do not matter.

    ``finditer`` rather than ``findall`` on purpose: a pattern that grows a
    capture group would silently start returning tuples, and the failure would be
    an ``AttributeError`` on a visitor's turn.
    """
    found = [
        m.group(0).replace(",", "").replace(" ", "").lower()
        for m in pattern.finditer(text)
    ]
    return tuple(sorted(found))


@dataclass(frozen=True)
class Facts:
    """Everything about a reply that a rephrasing is not allowed to change.

    Compared by equality, which is the point: the check is not "are the original
    facts still here" but "are these the same facts", so an invented figure fails
    for the same reason a deleted one does.
    """

    money: tuple[str, ...] = ()
    numbers: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    emails: tuple[str, ...] = ()
    links: tuple[str, ...] = ()
    products: frozenset[str] = frozenset()
    commitments: frozenset[str] = frozenset()
    asks_a_question: bool = False


def extract_facts(text: str) -> Facts:
    """Read the facts out of a reply.

    Money is taken out of the text before bare numbers are counted, so an amount
    is one fact and not also two digit-groups. Without that, "₦31,000" and
    "31,000 conversations" would be indistinguishable to the verifier.
    """
    money = _multiset(_MONEY, text)
    remainder = _MONEY.sub(" ", text)

    return Facts(
        money=money,
        numbers=_multiset(_NUMBER, remainder),
        references=_multiset(_REFERENCE, text),
        emails=_multiset(_EMAIL, text),
        links=_multiset(_LINK, text),
        products=frozenset(
            name for name in PRODUCT_NAMES.values() if name.lower() in text.lower()
        ),
        commitments=frozenset(
            m.group(0).lower() for m in _COMMITMENTS.finditer(text)
        ),
        # A reply that asks something is how the intake advances. A rephrasing
        # that drops the question reads fine and stalls the conversation, because
        # the buyer has nothing to answer.
        asks_a_question="?" in text,
    )


def disagreement(original: str, candidate: str) -> str | None:
    """Why this candidate may not be sent, or None if it may.

    Returns a reason rather than a boolean so the log says what the model did.
    A rejection is routine and not an error — it means the deterministic text
    ships, which is the behaviour without this module at all.
    """
    if not candidate or not candidate.strip():
        return "empty"

    if _META_PREAMBLE.search(candidate):
        return "answered the instruction instead of following it"

    length = len(candidate) / max(len(original), 1)
    if length > _MAX_LENGTH_RATIO:
        return f"too long ({length:.1f}x)"
    if length < _MIN_LENGTH_RATIO:
        return f"too short ({length:.1f}x)"

    before = extract_facts(original)
    after = extract_facts(candidate)

    if before.money != after.money:
        return f"amounts changed: {before.money} -> {after.money}"

    if before.numbers != after.numbers:
        return f"numbers changed: {before.numbers} -> {after.numbers}"

    if before.references != after.references:
        return "a quote reference was changed or invented"

    if before.emails != after.emails:
        return "an email address was changed or invented"

    if before.links != after.links:
        return "a link was changed or invented"

    if before.products != after.products:
        # Either a product the buyer was offered has vanished, or one they were
        # not offered has appeared. The second is Nera claiming to build
        # something this reply never authorised it to mention.
        return f"products changed: {sorted(before.products)} -> {sorted(after.products)}"

    invented = after.commitments - before.commitments
    if invented:
        return f"introduced a commitment: {sorted(invented)}"

    if before.asks_a_question and not after.asks_a_question:
        return "dropped the question the reply was asking"

    return None


# ---------- talking to the model ----------

_SYSTEM_PROMPT = (
    "You rewrite short customer-service messages so they read like a confident, "
    "warm professional wrote them. You are not answering the customer and you "
    "are not adding anything.\n\n"
    "Absolute rules:\n"
    "- Keep every number, price, product name, reference code, email and link "
    "exactly as written. Do not reformat, round, convert or spell them out.\n"
    "- Do not add offers, discounts, guarantees, promises, timeframes or "
    "capabilities. If the message does not claim something, neither do you.\n"
    "- Keep any question the message asks, as a question.\n"
    "- Keep it the same length or shorter. Never longer.\n"
    "- Reply with the rewritten message only. No preamble, no quotes, no "
    "options, no commentary.\n\n"
    "If you cannot improve it within those rules, reply with the message "
    "unchanged."
)


class Transport(Protocol):
    """Just enough of httpx for this client, so tests can hand in a fake."""

    def post(self, url: str, **kwargs: Any) -> httpx.Response: ...


class _HttpxTransport:
    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(timeout=self._timeout) as client:
            return client.post(url, **kwargs)


class Rephraser:
    """Groq, wrapped so that it cannot fail loudly.

    Every method returns text. A missing key, a timeout, a 500, malformed JSON
    and a candidate that fails verification all produce the same outcome — the
    input, unchanged — because a buyer waiting on a chat reply is better served
    by plain wording than by an error.
    """

    def __init__(
        self,
        api_key: str | None = None,
        transport: Transport | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._key = api_key if api_key is not None else settings.GROQ_API_KEY
        self._base = (base_url or settings.GROQ_BASE_URL).rstrip("/")
        self._model = model or settings.GROQ_MODEL
        self._transport = transport or _HttpxTransport(settings.LLM_TIMEOUT_SECONDS)

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    def _candidate(self, text: str) -> str | None:
        """One call to the model, or None if it could not be made or read."""
        try:
            response = self._transport.post(
                f"{self._base}/chat/completions",
                headers={
                    # Environment only. Never a CLI argument, never a log line.
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    # Low but not zero: the job is wording, and a deterministic
                    # decoder tends to return the input verbatim.
                    "temperature": 0.4,
                    # The reply is a chat message. A cap keeps a runaway
                    # generation from being paid for before it is rejected.
                    "max_tokens": 400,
                },
            )
        except Exception as exc:  # noqa: BLE001 - any failure means fall back
            logger.info("Rephrasing unavailable (%s); sending composed text", exc)
            return None

        if response.status_code >= 400:
            logger.info(
                "Rephrasing refused with %s; sending composed text",
                response.status_code,
            )
            return None

        try:
            choices = response.json()["choices"]
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError):
            logger.info("Rephrasing returned no usable text; sending composed text")
            return None

        if not isinstance(content, str):
            return None

        # Surrounding quotes are a formatting habit, not a change of meaning, so
        # they are stripped rather than rejected.
        return content.strip().strip('"').strip()

    def rephrase(self, text: str) -> str:
        """The same message, better worded — or the same message.

        Never raises, and never returns something that failed verification.
        """
        if not self.enabled or not text or not text.strip():
            return text

        candidate = self._candidate(text)
        if candidate is None:
            return text

        reason = disagreement(text, candidate)
        if reason is not None:
            # Routine. The composed text is correct on its own; this is the
            # verifier doing the job it exists for.
            logger.info("Rephrasing rejected (%s); sending composed text", reason)
            return text

        return candidate


def rephrase(text: str, *, rephraser: Rephraser | None = None) -> str:
    """Module-level convenience, so a call site needs no construction.

    One function for every channel. The widget, Telegram and WhatsApp all reach
    it through ``app.sales.service``, which is what keeps the wording consistent
    rather than per-channel.
    """
    return (rephraser or Rephraser()).rephrase(text)
