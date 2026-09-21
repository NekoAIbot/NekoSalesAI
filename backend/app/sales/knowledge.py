"""Authoritative context for the conversational layer.

One read-only interface to everything the conversation may reason over:
the catalog, the current configuration, and what the pricing engine would
charge for it. The LLM (or the deterministic fallback) receives these facts
rather than being trusted to remember them.

Nothing in this module computes a price the buyer is quoted — that remains
``app.pricing.complexity.price`` called by the agent at quote time. This is
the *context* layer: what is true, so the conversation cannot invent it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.pricing.complexity import (
    CHANNEL_ADD_MINOR,
    CHANNEL_NAMES,
    INTEGRATION_ADD_MINOR,
    LANGUAGES,
    MAX_INTEGRATIONS,
    MAX_LANGUAGES,
    MAX_QUOTABLE_CONVERSATIONS,
    PRODUCT_DESCRIPTIONS,
    PRODUCT_NAMES,
    PRODUCT_ORDER,
    Requirement,
    format_money,
)
from app.sales.scoping import Scope, answer as scoping_answer

# What each product genuinely does — the canonical capability statements.
# Every line is either the catalog description or a capability the pricing
# engine bills for. This is the only place product knowledge is stated for
# the conversational layer, and it is derived, not invented.
PRODUCT_CAPABILITIES: dict[str, dict] = {
    "sales_agent": {
        "name": PRODUCT_NAMES["sales_agent"],
        "does": "answers buyers, quotes your published prices, takes payment, follows up",
        "can": [
            "answer buyer questions",
            "quote published prices",
            "take payment through Paystack",
            "follow up when an order is not completed",
        ],
        "cannot": [
            "answer from a knowledge base it was not given",
            "give a discount without approval",
        ],
        "needs_integration_for": {
            "live stock levels": "inventory integration",
            "order sync to a CRM": "CRM integration",
        },
    },
    "support_agent": {
        "name": PRODUCT_NAMES["support_agent"],
        "does": "answers questions from your own material, escalates commercial queries",
        "can": [
            "answer questions from your published material",
            "escalate anything commercial to a person",
            "work around the clock",
        ],
        "cannot": [
            "quote prices or take payment",
            "complete a sale on its own",
        ],
        "needs_integration_for": {
            "live stock levels": "inventory integration",
        },
    },
    "workforce_agent": {
        "name": PRODUCT_NAMES["workforce_agent"],
        "does": "sales and support operating as one team, shared context",
        "can": [
            "everything the sales agent can",
            "everything the support agent can",
            "share one memory of each buyer across both roles",
        ],
        "cannot": [
            "give a discount without approval",
            "answer from material it was not given",
        ],
        "needs_integration_for": {
            "live stock levels": "inventory integration",
            "order sync to a CRM": "CRM integration",
        },
    },
}


@dataclass(frozen=True)
class CatalogContext:
    """The canonical catalog, as plain data for reasoning over."""

    products: tuple[dict, ...]
    channels: tuple[dict, ...]
    languages: tuple[dict, ...]
    limits: dict


def catalog_context() -> CatalogContext:
    """The catalog the conversation may reference. Never invented."""
    return CatalogContext(
        products=tuple(
            {
                "code": code,
                "name": PRODUCT_NAMES[code],
                "description": PRODUCT_DESCRIPTIONS[code],
                "capabilities": PRODUCT_CAPABILITIES[code]["can"],
                "cannot": PRODUCT_CAPABILITIES[code]["cannot"],
            }
            for code in PRODUCT_ORDER
        ),
        channels=tuple(
            {
                "code": code,
                "name": CHANNEL_NAMES[code],
                "add_minor": CHANNEL_ADD_MINOR[code],
                "included": CHANNEL_ADD_MINOR[code] == 0,
            }
            for code in CHANNEL_ADD_MINOR
        ),
        languages=tuple(
            {"code": code, "name": name} for code, name in LANGUAGES.items()
        ),
        limits={
            "max_integrations": MAX_INTEGRATIONS,
            "max_languages": MAX_LANGUAGES,
            "max_monthly_conversations": MAX_QUOTABLE_CONVERSATIONS,
            "integration_add_minor": INTEGRATION_ADD_MINOR,
            "conversation_price_minor": 5_00,
        },
    )


@dataclass(frozen=True)
class ConfigurationContext:
    """Where the buyer's configuration stands right now."""

    complete: bool
    pending_step: str | None
    pending_question: str | None
    answered: dict
    missing: tuple[str, ...]

    # The valid choices for the pending step, when it is selectable.
    pending_options: tuple[dict, ...] = ()


def configuration_context(scope: Scope) -> ConfigurationContext:
    """The current configuration state, from the authoritative scope."""
    from app.sales.options import for_step

    pending = scope.next_step
    answered = {}
    for step in ("products", "channels", "monthly_conversations", "integrations", "languages"):
        val = getattr(scope, step, None)
        if val is not None:
            answered[step] = list(val) if isinstance(val, tuple) else val

    missing = []
    if pending is not None:
        missing = [pending]

    options = ()
    if pending is not None:
        step_options = for_step(pending)
        if not step_options.free_text:
            options = tuple(
                {"value": o.value, "label": o.label} for o in step_options.options
            )

    return ConfigurationContext(
        complete=scope.is_complete,
        pending_step=pending,
        pending_question=scope.question() if pending else None,
        answered=answered,
        missing=tuple(missing),
        pending_options=options,
    )


def describe_configuration(scope: Scope) -> str:
    """The buyer's current configuration, in words, for 'what have I selected?'."""
    if scope.is_empty:
        return "Nothing yet — we haven't started configuring."

    parts = []
    if scope.products:
        names = [PRODUCT_NAMES.get(p, p) for p in scope.products]
        parts.append("products: " + ", ".join(names))
    if scope.channels:
        names = [CHANNEL_NAMES.get(c, c) for c in scope.channels]
        parts.append("channels: " + ", ".join(names))
    if scope.monthly_conversations:
        parts.append(f"volume: {scope.monthly_conversations:,} conversations/month")
    if scope.integrations is not None:
        parts.append(f"integrations: {scope.integrations}")
    if scope.languages:
        names = [LANGUAGES.get(l, l) for l in scope.languages]
        parts.append("languages: " + ", ".join(names))

    if not parts:
        return "Nothing yet — we haven't started configuring."

    return "So far: " + "; ".join(parts) + "."


def apply_correction(scope: Scope, correction: dict) -> Scope | None:
    """Apply a buyer's correction to the scope. Returns the new scope or None.

    Corrections are the buyer's own words, so they always win. A correction
    that would empty a required field is refused (returns None) — the buyer is
    told to set it rather than left with a half-built configuration.
    """
    kind = correction.get("kind")

    if kind == "language":
        code = correction.get("remove")
        if scope.languages and code in scope.languages:
            kept = tuple(l for l in scope.languages if l != code)
            if not kept:
                return None
            from dataclasses import replace
            return replace(scope, languages=kept)

    if kind == "channel":
        if "remove" in correction:
            code = correction["remove"]
            if scope.channels and code in scope.channels:
                kept = tuple(c for c in scope.channels if c != code)
                if not kept:
                    return None
                from dataclasses import replace
                return replace(scope, channels=kept)
        if "only" in correction:
            code = correction["only"]
            from dataclasses import replace
            return replace(scope, channels=(code,))
        if "add" in correction:
            code = correction["add"]
            if scope.channels and code not in scope.channels:
                from dataclasses import replace
                return replace(scope, channels=scope.channels + (code,))

    if kind == "volume":
        value = correction.get("value")
        if isinstance(value, int) and 0 < value <= MAX_QUOTABLE_CONVERSATIONS:
            from dataclasses import replace
            return replace(scope, monthly_conversations=value)

    return None
