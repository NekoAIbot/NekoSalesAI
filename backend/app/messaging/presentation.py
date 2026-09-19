"""Turning a scoping reply into channel-specific interactive controls.

Each channel gets the same underlying message from the agent — this module
adds the *controls* that make the step interactive: inline keyboards on
Telegram, numbered lists on WhatsApp. It never composes the agent's words;
it only appends structure the buyer can act on without typing.

The same ``StepOptions`` drives every renderer, so the three surfaces cannot
disagree about what a step offers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.sales.options import StepOptions, for_step


_CALLBACK_PREFIX = "scoping:"


@dataclass(frozen=True)
class ChannelMessage:
    """One message to send on a channel, with platform-specific controls."""

    text: str
    telegram_inline_keyboard: tuple[tuple[dict[str, str], ...], ...] = ()
    whatsapp_list_rows: tuple[dict[str, str], ...] = ()
    whatsapp_list_header: str = ""
    whatsapp_list_button: str = "Select"
    free_text: bool = False


def _telegram_keyboard(step: StepOptions) -> tuple[tuple[dict[str, str], ...], ...]:
    """Inline keyboard for a selectable scoping step."""
    if step.free_text or not step.options:
        return ()

    rows: list[tuple[dict[str, str], ...]] = []

    if step.multi:
        for opt in step.options:
            rows.append(
                (
                    {
                        "text": f"{opt.emoji} {opt.label}" if opt.emoji else opt.label,
                        "callback_data": f"{_CALLBACK_PREFIX}{step.step}:{opt.value}",
                    },
                )
            )
        rows.append(
            ({"text": "➡️ Next", "callback_data": f"{_CALLBACK_PREFIX}{step.step}:__next__"},)
        )
    else:
        for opt in step.options:
            label = f"{opt.emoji} {opt.label}" if opt.emoji else opt.label
            if opt.description and opt.description != "included":
                label = f"{label} — {opt.description}"
            rows.append(
                (
                    {
                        "text": label,
                        "callback_data": f"{_CALLBACK_PREFIX}{step.step}:{opt.value}",
                    },
                )
            )

    return tuple(rows)


def _whatsapp_list(step: StepOptions) -> tuple[tuple[dict[str, str], ...], str]:
    """Numbered list for a selectable scoping step."""
    if step.free_text or not step.options:
        return (), ""

    rows: list[dict[str, str]] = []
    for i, opt in enumerate(step.options, 1):
        title = f"{opt.emoji} {opt.label}" if opt.emoji else opt.label
        desc = opt.description or ""
        rows.append(
            {
                "id": f"{step.step}:{opt.value}",
                "title": title,
                "description": desc,
            }
        )

    return tuple(rows), "Options"


def render_step(
    text: str,
    step: str,
    *,
    hint: str = "",
) -> ChannelMessage:
    """Render a scoping step as a channel-specific interactive message."""
    options = for_step(step)

    if hint:
        text = f"{text}\n\n{hint}"
    elif options.free_text and options.hint:
        text = f"{text}\n\n{options.hint}"

    if options.free_text or not options.options:
        return ChannelMessage(text=text, free_text=options.free_text)

    kb = _telegram_keyboard(options)
    rows, header = _whatsapp_list(options)

    return ChannelMessage(
        text=text,
        free_text=False,
        telegram_inline_keyboard=kb,
        whatsapp_list_rows=rows,
        whatsapp_list_header=header,
    )


def parse_callback(data: str) -> tuple[str, str] | None:
    """Parse a Telegram callback data string into (step, value)."""
    if not data.startswith(_CALLBACK_PREFIX):
        return None
    payload = data[len(_CALLBACK_PREFIX):]
    _, sep, value = payload.partition(":")
    if not sep:
        return None
    return (_, value)


def callback_for(step: str, value: str) -> str:
    """Build a callback_data string for a scoping option."""
    return f"{_CALLBACK_PREFIX}{step}:{value}"
