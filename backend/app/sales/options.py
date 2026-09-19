"""Structured options for each scoping step, keyed by ``Scope.next_step``.

A scoping step is either *selectable* (a bounded set the buyer picks from)
or *free_text* (the parser needs a number or a sentence). Selectable steps get
buttons on Telegram, a list on WhatsApp, and chips on the widget; free-text
steps stay a plain question.

Nothing here invents products, channels, integrations or languages. Each list
is generated from the canonical catalog in ``app.pricing.complexity`` — there is
no second source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from app.pricing.complexity import (
    CHANNEL_ADD_MINOR,
    CHANNEL_EMAIL,
    CHANNEL_NAMES,
    CHANNEL_TELEGRAM,
    CHANNEL_WEB,
    CHANNEL_WHATSAPP,
    INTEGRATION_LABELS,
    LANGUAGES,
    PRODUCT_DESCRIPTIONS,
    PRODUCT_NAMES,
    PRODUCT_ORDER,
)


@dataclass(frozen=True)
class Option:
    """One selectable choice the buyer can tap."""

    # What the scoping parser recognises — what we feed back to the agent.
    value: str
    # What the buyer sees on the button / list row.
    label: str
    # A short line under the label — the "from ₦X" or "₦Y / month".
    description: str = ""
    # Emoji or short mark prepended by some renderers. Optional.
    emoji: str = ""


@dataclass(frozen=True)
class StepOptions:
    """The options one scoping step offers, or free-text instructions."""

    step: str
    # When True the buyer types a number or sentence; no buttons are shown.
    free_text: bool = False
    # The bounded choices, when there are any.
    options: tuple[Option, ...] = ()
    # For multi-select steps (channels, languages) vs single-select (product).
    multi: bool = False
    # A one-line hint for free-text steps.
    hint: str = ""


# Channel display order — web first since every build ships with it.
_DISPLAY_CHANNELS = (
    CHANNEL_WEB,
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    CHANNEL_EMAIL,
)


def _channel_option(code: str) -> Option:
    name = CHANNEL_NAMES[code]
    add = CHANNEL_ADD_MINOR[code]
    if add == 0:
        return Option(value=code, label=name, description="included", emoji="🌐" if code == CHANNEL_WEB else "📨")
    return Option(
        value=code,
        label=name,
        description=f"₦{add // 100:,} / month",
        emoji="✈️" if code == CHANNEL_TELEGRAM else "📱" if code == CHANNEL_WHATSAPP else "📨",
    )


def _integration_options() -> tuple[Option, ...]:
    return tuple(
        Option(value=code, label=name, description="₦2,000 / month", emoji="🔌")
        for code, name in INTEGRATION_LABELS.items()
    )


def _language_options() -> tuple[Option, ...]:
    return tuple(
        Option(value=code, label=name, emoji="🗣️")
        for code, name in LANGUAGES.items()
    )


def _product_options() -> tuple[Option, ...]:
    return tuple(
        Option(
            value=code,
            label=PRODUCT_NAMES[code],
            description=PRODUCT_DESCRIPTIONS[code],
            emoji="🤖",
        )
        for code in PRODUCT_ORDER
    )


def for_step(step: str) -> StepOptions:
    """The options a scoping step offers, for renderers to turn into UI."""
    if step == "products":
        return StepOptions(step=step, options=_product_options(), multi=False)
    if step == "channels":
        return StepOptions(
            step=step,
            options=tuple(_channel_option(c) for c in _DISPLAY_CHANNELS),
            multi=True,
        )
    if step == "integrations":
        return StepOptions(
            step=step,
            free_text=True,
            hint="Say a number — 0 for none, up to 10.",
        )
    if step == "monthly_conversations":
        return StepOptions(
            step=step,
            free_text=True,
            hint="A number is fine — say 500, 2,000, 10,000.",
        )
    if step == "languages":
        return StepOptions(
            step=step,
            options=_language_options(),
            multi=True,
        )
    return StepOptions(step=step, free_text=True)
