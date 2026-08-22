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

        response = self._transport.post(
            f"{self._base}/bot{self._token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                # Plain text on purpose. Follow-up copy is written by
                # app.followups.rules and can contain characters Telegram's
                # Markdown parser would reject, which would fail the send over a
                # stray underscore in a company name.
                "disable_web_page_preview": True,
            },
        )

        self._raise_for_response(response, chat_id)

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

        response = self._transport.post(
            f"{self._base}/{self._phone_number_id}/messages",
            headers={"Authorization": f"Bearer {self._token}"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_number,
                "type": "text",
                "text": {"preview_url": False, "body": text},
            },
        )

        if response.status_code >= 400:
            raise MessagingError(
                f"WhatsApp refused a message to {to_number}: "
                f"{response.status_code} {response.text[:200]}"
            )
