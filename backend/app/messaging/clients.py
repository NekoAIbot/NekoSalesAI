"""Telegram and WhatsApp, as places a message can be sent.

Same shape as ``app.payments.paystack``, and for the same reasons: the transport
is injectable so every path is exercised without an account, a network, or
anyone's real token in a fixture; and a missing token raises a distinct error
rather than producing a request that will 401. "This deployment has not been set
up" and "something is broken" need different answers at the call site.

These clients only send. Receiving — a buyer talking to Nera on either platform —
is webhook-driven and lives in ``app.api.v1.routes.messaging``.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.config.logging import get_logger
from app.config.settings import settings

logger = get_logger(__name__)


class MessagingNotConfigured(RuntimeError):
    """No credential for this channel, so it cannot be used."""


class MessagingError(RuntimeError):
    """The platform was reached and refused, or answered something unusable."""


# Telegram rejects a sendMessage body over 4,096 characters, and WhatsApp's text
# body limit is the same figure. Left a little under it so a platform counting
# code points differently than Python does cannot turn a borderline message into
# a refusal.
MESSAGE_LIMIT = 3_900


def split_for_delivery(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Break a long message on a boundary a reader would have chosen.

    A safety net rather than a formatter. Delivery already composes itself as
    several right-sized messages, and callers with real copy should keep doing
    that — but "the text got longer than the platform allows" must never be the
    reason a buyer who paid hears nothing. Before this, an over-long send came
    back as a rejection, was logged, swallowed, and looked exactly like a chat
    platform being down.

    Splits on the largest boundary that fits: blank lines first, then single
    lines, and only cuts mid-line when one line is itself longer than the limit.
    That keeps the widget snippet and the numbered install steps intact, which is
    the whole point — instructions chopped through the middle of a ``<script>``
    tag are worse than no instructions.
    """
    if len(text) <= limit:
        return [text]

    pieces: list[str] = []

    for block in _grouped(text.split("\n\n"), limit, joiner="\n\n"):
        if len(block) <= limit:
            pieces.append(block)
            continue

        for line_group in _grouped(block.split("\n"), limit, joiner="\n"):
            if len(line_group) <= limit:
                pieces.append(line_group)
                continue

            # One unbroken line longer than the limit. Nothing to preserve, so
            # cut it into limit-sized pieces rather than drop it.
            pieces.extend(
                line_group[start:start + limit]
                for start in range(0, len(line_group), limit)
            )

    return [piece for piece in pieces if piece.strip()] or [text[:limit]]


def _grouped(chunks: list[str], limit: int, *, joiner: str) -> list[str]:
    """Pack chunks into as few groups as fit under the limit, in order."""
    groups: list[str] = []
    current = ""

    for chunk in chunks:
        candidate = f"{current}{joiner}{chunk}" if current else chunk

        if current and len(candidate) > limit:
            groups.append(current)
            current = chunk
        else:
            current = candidate

    if current:
        groups.append(current)

    return groups


class Transport(Protocol):
    """Just enough of httpx for these clients, so tests can hand in a fake."""

    def post(self, url: str, **kwargs: Any) -> httpx.Response: ...


class _HttpxTransport:
    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(timeout=self._timeout) as client:
            return client.post(url, **kwargs)


class TelegramClient:
    """Sends a message through the Bot API."""

    def __init__(
        self,
        bot_token: str | None = None,
        transport: Transport | None = None,
        base_url: str | None = None,
    ) -> None:
        self._token = bot_token if bot_token is not None else settings.TELEGRAM_BOT_TOKEN
        self._base = (base_url or settings.TELEGRAM_BASE_URL).rstrip("/")
        self._transport = transport or _HttpxTransport(settings.MESSAGING_TIMEOUT)

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def send_message(self, chat_id: str, text: str) -> None:
        if not self._token:
            raise MessagingNotConfigured("TELEGRAM_BOT_TOKEN is not set.")

        for piece in split_for_delivery(text):
            response = self._transport.post(
                f"{self._base}/bot{self._token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": piece,
                    "disable_web_page_preview": True,
                },
            )

            self._raise_for_response(response, chat_id)

    def send_message_with_keyboard(
        self,
        chat_id: str,
        text: str,
        inline_keyboard: list[list[dict[str, str]]],
    ) -> None:
        """Send a message with an inline keyboard.

        ``inline_keyboard`` is a list of rows, each a list of buttons with
        ``text`` and ``callback_data`` keys.
        """
        if not self._token:
            raise MessagingNotConfigured("TELEGRAM_BOT_TOKEN is not set.")

        for piece in split_for_delivery(text):
            response = self._transport.post(
                f"{self._base}/bot{self._token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": piece,
                    "disable_web_page_preview": True,
                    "reply_markup": {"inline_keyboard": inline_keyboard},
                },
            )

            self._raise_for_response(response, chat_id)

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        """Acknowledge a button press so Telegram stops the loading spinner."""
        if not self._token:
            return

        try:
            response = self._transport.post(
                f"{self._base}/bot{self._token}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
            )
            self._raise_for_response(response, f"callback:{callback_query_id}")
        except MessagingError:
            pass  # An answering failure is not worth a retry

    @staticmethod
    def _raise_for_response(response: httpx.Response, chat_id: str) -> None:
        if response.status_code >= 400:
            raise MessagingError(
                f"Telegram refused a message to {chat_id}: "
                f"{response.status_code} {response.text[:200]}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise MessagingError("Telegram returned a non-JSON response.") from exc

        # A 200 with ok=false is Telegram's way of reporting a rejected send.
        if not body.get("ok", False):
            raise MessagingError(
                f"Telegram rejected a message to {chat_id}: "
                f"{body.get('description', 'no reason given')}"
            )


class WhatsAppClient:
    """Sends a message through the Meta Cloud API."""

    def __init__(
        self,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        transport: Transport | None = None,
        base_url: str | None = None,
    ) -> None:
        self._token = (
            access_token if access_token is not None else settings.WHATSAPP_ACCESS_TOKEN
        )
        self._phone_number_id = (
            phone_number_id
            if phone_number_id is not None
            else settings.WHATSAPP_PHONE_NUMBER_ID
        )
        self._base = (base_url or settings.WHATSAPP_BASE_URL).rstrip("/")
        self._transport = transport or _HttpxTransport(settings.MESSAGING_TIMEOUT)

    @property
    def configured(self) -> bool:
        return bool(self._token and self._phone_number_id)

    def send_message(self, to_number: str, text: str) -> None:
        if not self.configured:
            raise MessagingNotConfigured(
                "WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID must both be set."
            )

        for piece in split_for_delivery(text):
            response = self._transport.post(
                f"{self._base}/{self._phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self._token}"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to_number,
                    "type": "text",
                    "text": {"preview_url": False, "body": piece},
                },
            )

            if response.status_code >= 400:
                raise MessagingError(
                    f"WhatsApp refused a message to {to_number}: "
                    f"{response.status_code} {response.text[:200]}"
                )

    def send_interactive_list(
        self,
        to_number: str,
        text: str,
        header: str,
        button: str,
        rows: list[dict[str, str]],
    ) -> None:
        """Send an interactive list message on WhatsApp.

        ``rows`` is a list of dicts with ``id``, ``title``, and optionally
        ``description`` keys.
        """
        if not self.configured:
            raise MessagingNotConfigured(
                "WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID must both be set."
            )

        for piece in split_for_delivery(text):
            response = self._transport.post(
                f"{self._base}/{self._phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self._token}"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to_number,
                    "type": "interactive",
                    "interactive": {
                        "type": "list",
                        "header": {"type": "text", "text": header},
                        "body": {"text": piece},
                        "action": {
                            "button": button,
                            "sections": [{"title": header, "rows": rows}],
                        },
                    },
                },
            )

            if response.status_code >= 400:
                raise MessagingError(
                    f"WhatsApp refused a message to {to_number}: "
                    f"{response.status_code} {response.text[:200]}"
                )
