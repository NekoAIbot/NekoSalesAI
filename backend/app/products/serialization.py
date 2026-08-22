"""Reading and writing a ProductConfig as JSON.

A customer's config is a database row, because customers set their own. That
means it crosses a trust boundary in both directions: written by a form a
customer filled in, read back into an object whose contents the agent will say
out loud. So parsing is strict about shape and paranoid about provenance.

Two rules earn their keep here.

**Anything loaded from a row is DECLARED unless we put it there.** ``verified``
means "there is code in this repo implementing it, and a test asserts the
module resolves". A row cannot make that true about itself. If stored JSON
claims ``source: verified``, that claim is downgraded on load rather than
honoured — otherwise a customer editing their own profile could promote their
marketing copy into a claim the agent states in our voice. The storefront's
verified claims live in ``app.catalog.products`` as Python, not in a row, which
is what makes them assertable.

**Bad JSON degrades to a safe config, never to a crash and never to a guess.**
A malformed row means an agent with nothing to say, which routes every question
to a human. That is the correct failure: no prices, no claims, no promises.
"""

from __future__ import annotations

import json

from app.products.config import (
    BUILDABLE_ROLES,
    ROLE_SALES_AGENT,
    SOURCE_DECLARED,
    Capability,
    Faq,
    Plan,
    ProductConfig,
)


class ConfigParseError(ValueError):
    """Stored config could not be read as a config."""


def config_to_dict(config: ProductConfig) -> dict:
    """Serialize for storage.

    Round-trips through ``config_from_dict`` in every field except capability
    provenance, which is intentionally lossy: see the module docstring. A
    storefront config written and read back has the same claims, marked
    declared.
    """
    return {
        "company_name": config.company_name,
        "tagline": config.tagline,
        "description": config.description,
        "support_email": config.support_email,
        "agent_name": config.agent_name,
        "role": config.role,
        "max_auto_discount_percent": config.max_auto_discount_percent,
        "plans": [
            {
                "code": plan.code,
                "name": plan.name,
                "audience": plan.audience,
                "currency": plan.currency,
                "amount_minor": plan.amount_minor,
                "billing_period": plan.billing_period,
                "seats": plan.seats,
                "monthly_conversation_limit": plan.monthly_conversation_limit,
                "features": list(plan.features),
                "is_default": plan.is_default,
            }
            for plan in config.plans
        ],
        # Claim text only. ``source`` and ``verified_by`` are deliberately not
        # written: the loader downgrades every stored claim to DECLARED, so
        # persisting them would imply a guarantee the row cannot carry.
        "capabilities": [{"claim": c.claim} for c in config.capabilities],
        "faqs": [{"question": f.question, "answer": f.answer} for f in config.faqs],
        "knowledge": [
            {"question": k.question, "answer": k.answer} for k in config.knowledge
        ],
    }


def config_to_json(config: ProductConfig) -> str:
    return json.dumps(config_to_dict(config))


def _text(data: dict, key: str, default: str = "") -> str:
    value = data.get(key, default)
    return value.strip() if isinstance(value, str) else default


def _int(data: dict, key: str, default: int) -> int:
    value = data.get(key, default)

    # bool is an int subclass, and True would silently become a price of 1.
    if isinstance(value, bool) or not isinstance(value, int):
        return default

    return value


def _pairs(raw: object) -> tuple[Faq, ...]:
    """Parse question/answer pairs, dropping any that are not both present."""
    if not isinstance(raw, list):
        return ()

    pairs = []

    for entry in raw:
        if not isinstance(entry, dict):
            continue

        question = _text(entry, "question")
        answer = _text(entry, "answer")

        if question and answer:
            pairs.append(Faq(question=question, answer=answer))

    return tuple(pairs)


def _plans(raw: object) -> tuple[Plan, ...]:
    if not isinstance(raw, list):
        return ()

    plans = []
    seen: set[str] = set()

    for entry in raw:
        if not isinstance(entry, dict):
            continue

        code = _text(entry, "code")
        amount_minor = _int(entry, "amount_minor", -1)

        # A plan with no code cannot be looked up, and a negative price is not
        # a price. Either way the entry is unusable, so drop it rather than
        # let the agent quote it.
        if not code or code in seen or amount_minor < 0:
            continue

        seen.add(code)

        features = entry.get("features")
        features = tuple(
            f.strip() for f in features
            if isinstance(f, str) and f.strip()
        ) if isinstance(features, list) else ()

        plans.append(
            Plan(
                code=code,
                name=_text(entry, "name") or code,
                audience=_text(entry, "audience"),
                currency=_text(entry, "currency") or "NGN",
                amount_minor=amount_minor,
                billing_period=_text(entry, "billing_period") or "month",
                seats=max(_int(entry, "seats", 1), 0),
                monthly_conversation_limit=max(
                    _int(entry, "monthly_conversation_limit", 0), 0
                ),
                features=features,
                is_default=bool(entry.get("is_default", False)),
            )
        )

    return tuple(plans)


def _capabilities(raw: object) -> tuple[Capability, ...]:
    """Parse claims. Every one is DECLARED — see the module docstring."""
    if not isinstance(raw, list):
        return ()

    capabilities = []

    for entry in raw:
        if isinstance(entry, str):
            claim = entry.strip()
        elif isinstance(entry, dict):
            claim = _text(entry, "claim")
        else:
            continue

        if not claim:
            continue

        capabilities.append(Capability(claim=claim, source=SOURCE_DECLARED))

    return tuple(capabilities)


def config_from_dict(data: dict) -> ProductConfig:
    """Build a config from stored data. Raises ``ConfigParseError`` on junk."""
    if not isinstance(data, dict):
        raise ConfigParseError("Stored config is not an object.")

    company_name = _text(data, "company_name")

    if not company_name:
        # Without a name the agent cannot introduce itself or attribute a
        # claim to anyone, so there is nothing coherent to build.
        raise ConfigParseError("Stored config has no company_name.")

    discount = _int(data, "max_auto_discount_percent", 0)

    # Clamped rather than rejected: a nonsense ceiling should not take the
    # agent offline, and clamping toward zero always tightens, never loosens.
    discount = min(max(discount, 0), 100)

    # An unrecognised role falls back to the sales agent rather than raising:
    # that is the behaviour every config written before Stage D had, so a row
    # from an older release keeps working. Widening a role is a decision the
    # factory makes at provisioning time, not something a junk string does.
    #
    # Checked against BUILDABLE_ROLES, not every role that exists. "builder" is
    # a real role but not a shippable one — a row claiming it would be a
    # customer's own product asserting it is the factory. There is no path that
    # writes that today; this is what keeps it that way if one is ever added.
    role = _text(data, "role")
    if role not in BUILDABLE_ROLES:
        role = ROLE_SALES_AGENT

    return ProductConfig(
        company_name=company_name,
        tagline=_text(data, "tagline"),
        description=_text(data, "description"),
        support_email=_text(data, "support_email"),
        agent_name=_text(data, "agent_name") or "the sales rep",
        role=role,
        plans=_plans(data.get("plans")),
        capabilities=_capabilities(data.get("capabilities")),
        faqs=_pairs(data.get("faqs")),
        knowledge=_pairs(data.get("knowledge")),
        max_auto_discount_percent=discount,
    )


def config_from_json(raw: str | None) -> ProductConfig | None:
    """Parse a stored row. Returns None when there is nothing usable.

    None means "this workspace has no config", which callers resolve to a
    minimal safe config. It never means "use the storefront's" — quoting our
    prices to a customer's buyers is the exact bug Stage A exists to fix.
    """
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    try:
        return config_from_dict(data)
    except (ConfigParseError, ValueError):
        return None
