"""LLM semantic understanding, on the existing Groq provider.

The deterministic engine stays the system of record. This layer exists for
the messages regex cannot read: "can it basically run my sales side while I
focus on the business?", "what's the point of having both agents?", "forget
what I said about Hausa". The model interprets; the application validates
and applies.

Contract with the caller:

- ``understand(message, context)`` returns a ``SemanticResult`` or ``None``.
  None means "no LLM available / call failed / nothing usable" and the
  caller proceeds exactly as it does today — deterministic rules only.
- Every field the model returns is treated as a *suggestion*. Products,
  channels, languages are normalized against the canonical catalogs before
  anything reaches the scope. A hallucinated product never survives.
- The model never sees or sets prices, payment state or provisioning state.
  Its structured output has nowhere to put them, on purpose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config.logging import get_logger
from app.config.settings import settings
from app.pricing.complexity import (
    CHANNEL_ADD_MINOR,
    LANGUAGES,
    PRODUCT_ORDER,
)
from app.sales.context import EXTRACTED, INFERRED, STATED

logger = get_logger(__name__)


class Transport(Protocol):
    """Same shape as the rephraser's transport, so tests can hand in a fake."""

    def post(self, url: str, **kwargs: Any) -> httpx.Response: ...


class _HttpxTransport:
    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(timeout=self._timeout) as client:
            return client.post(url, **kwargs)


# The intent vocabulary. Deliberately small and matching the deterministic
# intents in app.sales.understanding so the two layers compose rather than
# compete.
_INTENTS = ("question", "configuration", "correction", "recommendation",
            "pricing", "continue", "greeting", "other")

_SYSTEM_PROMPT = """You interpret one message from a business owner talking to Nera, an AI that builds AI sales/support agents for small businesses.

Return ONLY a JSON object, no prose, no markdown fences, with these keys:
- "intent": one of question, configuration, correction, recommendation, pricing, continue, greeting, other
- "products": product codes the customer explicitly wants, from: sales_agent, support_agent, workforce_agent (empty if none)
- "channels": channels mentioned, from: web, telegram, whatsapp, email (empty if none)
- "languages": language codes mentioned, from: en, yo, ha, ig, pid (empty if none)
- "volume": integer monthly conversations if stated, else null
- "integrations": integer integration count if stated, else null
- "remove": codes the customer wants removed (channels or languages), empty if none
- "business_type": short business category if stated (e.g. "clothing", "pharmacy"), else null
- "goals": what the customer wants the AI to do, as short snake_case tags (e.g. sell, take_orders, answer_questions, follow_up), empty if none
- "topic": if the message is a question, what it asks about in a few words, else null
- "confidence": your confidence from 0.0 to 1.0

Rules:
- Only include what the customer actually said or clearly meant. Do not invent.
- Never mention prices, payment, or provisioning — those are not yours to state.
- If the message is ambiguous, lower the confidence rather than guessing.
"""


@dataclass(frozen=True)
class SemanticResult:
    """One validated interpretation of a customer message."""

    intent: str = "other"
    products: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    volume: int | None = None
    integrations: int | None = None
    remove: tuple[str, ...] = ()
    business_type: str | None = None
    goals: tuple[str, ...] = ()
    topic: str | None = None
    confidence: float = 0.0
    # True when the model produced this; False when the deterministic layer
    # did (the fallback path constructs the same shape).
    from_llm: bool = False


_VALID_PRODUCTS = set(PRODUCT_ORDER)
_VALID_CHANNELS = set(CHANNEL_ADD_MINOR)
_VALID_LANGUAGES = set(LANGUAGES)

# The model sometimes returns the human name or an alias rather than the
# canonical code. Map the common shapes; anything unmapped is dropped.
_PRODUCT_ALIASES: dict[str, str] = {
    "sales_agent": "sales_agent",
    "sales": "sales_agent",
    "salesagent": "sales_agent",
    "ai_sales_agent": "sales_agent",
    "ai sales agent": "sales_agent",
    "sales_rep": "sales_agent",
    "support_agent": "support_agent",
    "support": "support_agent",
    "supportagent": "support_agent",
    "ai_support_agent": "support_agent",
    "ai support agent": "support_agent",
    "workforce_agent": "workforce_agent",
    "workforce": "workforce_agent",
    "workforceagent": "workforce_agent",
    "both": "workforce_agent",
    "sales_and_support": "workforce_agent",
    "sales + support": "workforce_agent",
    "all": "workforce_agent",
}

_CHANNEL_ALIASES: dict[str, str] = {
    "web": "web",
    "website": "web",
    "site": "web",
    "web_widget": "web",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "wa": "whatsapp",
    "email": "email",
    "e_mail": "email",
}

_LANGUAGE_ALIASES: dict[str, str] = {
    "en": "en", "english": "en",
    "yo": "yo", "yoruba": "yo",
    "ha": "ha", "hausa": "ha",
    "ig": "ig", "igbo": "ig",
    "pid": "pid", "pidgin": "pid", "nigerian_pidgin": "pid",
}


def _clean_str_list(raw: Any, valid: set[str], aliases: dict[str, str] | None = None) -> tuple[str, ...]:
    """Map to canonical codes, keep only valid ones, in catalog order."""
    if not isinstance(raw, list):
        return ()

    mapped: list[str] = []
    for x in raw:
        if not isinstance(x, (str, int)):
            continue
        key = str(x).strip().lower()
        if aliases and key in aliases:
            mapped.append(aliases[key])
        elif key in valid:
            mapped.append(key)

    seen = [c for c in valid if c in set(mapped)]
    return tuple(seen)


def _clean_int(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str):
        digits = re.sub(r"[^\d]", "", raw)
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


def _validate(data: dict) -> SemanticResult:
    """Normalize the model's raw output against the canonical catalogs.

    Everything not in the canonical sets is dropped silently — a hallucinated
    product code never reaches the scope. ``intent`` falls back to "other"
    when unrecognized.
    """
    intent = str(data.get("intent", "other")).strip().lower()
    if intent not in _INTENTS:
        intent = "other"

    remove_raw = data.get("remove")
    remove = _clean_str_list(remove_raw, _VALID_CHANNELS | _VALID_LANGUAGES)

    goals_raw = data.get("goals")
    goals = ()
    if isinstance(goals_raw, list):
        goals = tuple(
            re.sub(r"[^a-z0-9_]", "", str(g).strip().lower())
            for g in goals_raw
            if isinstance(g, str) and g.strip()
        )[:6]

    business_type = data.get("business_type")
    business_type = (
        re.sub(r"[^a-z0-9_ ]", "", str(business_type).strip().lower())[:40] or None
        if isinstance(business_type, str) and business_type.strip()
        else None
    )

    topic = data.get("topic")
    topic = str(topic).strip()[:80] or None if isinstance(topic, str) else None

    confidence = 0.0
    if isinstance(data.get("confidence"), (int, float)):
        confidence = max(0.0, min(1.0, float(data["confidence"])))

    return SemanticResult(
        intent=intent,
        products=_clean_str_list(data.get("products"), _VALID_PRODUCTS, _PRODUCT_ALIASES),
        channels=_clean_str_list(data.get("channels"), _VALID_CHANNELS, _CHANNEL_ALIASES),
        languages=_clean_str_list(data.get("languages"), _VALID_LANGUAGES, _LANGUAGE_ALIASES),
        volume=_clean_int(data.get("volume")),
        integrations=_clean_int(data.get("integrations")),
        remove=_clean_str_list(
            data.get("remove"),
            _VALID_CHANNELS | _VALID_LANGUAGES,
            {**_CHANNEL_ALIASES, **_LANGUAGE_ALIASES},
        ),
        business_type=business_type,
        goals=goals,
        topic=topic,
        confidence=confidence,
        from_llm=True,
    )


def _extract_json(text: str) -> dict | None:
    """Pull the JSON object out of a model reply that may have wrapper prose."""
    if not text:
        return None
    # Try direct parse first.
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    # Then the first {...} block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None


class UnderstandingLLM:
    """The semantic-understanding client. Same provider as the rephraser."""

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
        self._transport = transport or _HttpxTransport(
            settings.LLM_UNDERSTANDING_TIMEOUT_SECONDS
        )
        # An explicitly-injected key means the caller (usually a test with a
        # fake transport) wants this client live regardless of the TESTING
        # flag; only the ambient .env key is suppressed under test.
        self._explicit_key = api_key is not None

    @property
    def enabled(self) -> bool:
        # Tests run the deterministic engine only — same reason as the
        # rephraser's guard. An explicitly-constructed client (fake transport,
        # injected key) stays on.
        from app.config.settings import settings as _settings

        if getattr(_settings, "TESTING", False) and not self._explicit_key:
            return False
        return bool(self._key)

    def understand(self, message: str, context_summary: str = "") -> SemanticResult | None:
        """Interpret one message. Returns None on any failure.

        ``context_summary`` is a short, structured description of what is
        known (see ``build_context_summary``) — enough for the model to
        resolve references like "that one" or "the second option" without
        sending a transcript.
        """
        if not self.enabled or not message or not message.strip():
            return None

        user_content = message.strip()
        if context_summary:
            user_content = f"Context so far:\n{context_summary}\n\nMessage: {message.strip()}"

        try:
            response = self._transport.post(
                f"{self._base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 600,
                    # No response_format: the JSON-extraction above handles
                    # wrapper prose, and json_object mode measured ~2.5s slower
                    # on this model.
                },
            )
        except Exception as exc:  # noqa: BLE001 - any failure means fall back
            logger.info("LLM understanding unavailable (%s); deterministic path", exc)
            return None

        # Rate limiting: fail fast into the deterministic path, never retry.
        # A 429 means the provider is asking us to slow down; hammering it
        # with retries would block the buyer's conversation and compound the
        # limit. The deterministic engine answers this turn and the next
        # message gets a fresh, single attempt.
        if response.status_code == 429:
            logger.info("LLM rate-limited; deterministic path for this turn")
            return None

        if response.status_code >= 400:
            logger.info(
                "LLM understanding refused with %s; deterministic path",
                response.status_code,
            )
            return None

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError):
            return None

        if not isinstance(content, str) or not content.strip():
            return None

        data = _extract_json(content)
        if data is None:
            logger.info("LLM understanding returned unparseable output; deterministic path")
            return None

        return _validate(data)


def build_context_summary(memory, scope) -> str:
    """A short, structured context for the model — not a transcript.

    Deliberately bounded: the buyer's facts, their goals, what is configured,
    and what question is pending. The model uses it to resolve references;
    it is never asked to remember the whole conversation.
    """
    lines: list[str] = []

    if memory is not None:
        for key, fact in list(memory.business.items())[:6]:
            lines.append(f"- business {key}: {fact.value}")
        for key, fact in list(memory.requirements.items())[:6]:
            lines.append(f"- requirement {key}: {fact.value}")
        if memory.recent_questions:
            last = memory.recent_questions[-2:]
            lines.append("- recent questions: " + " | ".join(last))

    if scope is not None:
        if scope.products:
            lines.append("- selected products: " + ", ".join(scope.products))
        if scope.channels:
            lines.append("- selected channels: " + ", ".join(scope.channels))
        if scope.monthly_conversations:
            lines.append(f"- volume: {scope.monthly_conversations}")
        if scope.integrations is not None:
            lines.append(f"- integrations: {scope.integrations}")
        if scope.languages:
            lines.append("- languages: " + ", ".join(scope.languages))
        pending = scope.next_step
        if pending:
            lines.append(f"- pending question: {pending.replace('_', ' ')}")

    return "\n".join(lines)
