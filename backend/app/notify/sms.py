"""Brevo SMS provider — follows the same pattern as app/mail/transport.py."""
from __future__ import annotations

import threading
from typing import Optional

import httpx

from app.config.logging import get_logger
from app.config.settings import settings

logger = get_logger(__name__)

BREVO_SMS_BASE_URL = "https://api.brevo.com/v3"


class SmsResult:
    """Whether an SMS was sent, and why not if it was not."""

    def __init__(self, sent: bool, error: str | None = None, message_id: str | None = None):
        self.sent = sent
        self.error = error
        self.message_id = message_id


class BrevoSmsProvider:
    """Sends SMS via Brevo API.

    Uses the shared BREVO_API_KEY for authentication.
    """

    def __init__(self) -> None:
        self._base_url = BREVO_SMS_BASE_URL
        self._timeout = 15.0

    def is_configured(self) -> bool:
        """Whether the provider has the required configuration."""
        return bool(settings.BREVO_API_KEY)

    def send(self, to: str, message: str, sender: str | None = None) -> SmsResult:
        """Send an SMS via Brevo.

        Args:
            to: Phone number in international format (e.g., +2348000000000)
            message: SMS body
            sender: Sender name (max 11 alphanumeric characters)

        Returns:
            SmsResult indicating success or failure
        """
        if not settings.BREVO_API_KEY:
            return SmsResult(sent=False, error="BREVO_API_KEY not configured")

        if not to:
            return SmsResult(sent=False, error="Recipient phone number required")

        if not message or not message.strip():
            return SmsResult(sent=False, error="SMS body cannot be empty")

        # Normalize phone number
        phone = self._normalize_phone(to)
        if not phone:
            return SmsResult(sent=False, error=f"Invalid phone number: {to}")

        # Use configured sender or default
        sender_name = sender or settings.MAIL_FROM_NAME[:11]  # Brevo limit: 11 chars

        headers = {
            "api-key": settings.BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        payload = {
            "sender": sender_name,
            "recipient": phone,
            "content": message.strip(),
            "type": "transactional"
        }

        try:
            resp = httpx.post(
                f"{self._base_url}/transactionalSMS/sms",
                headers=headers,
                json=payload,
                timeout=self._timeout
            )

            if resp.status_code == 201:
                data = resp.json()
                message_id = data.get("messageId") or data.get("reference")
                logger.info("SMS sent to %s via Brevo", phone)
                return SmsResult(sent=True, message_id=message_id)
            else:
                error_msg = f"Brevo SMS API error {resp.status_code}: {resp.text[:200]}"
                logger.error(error_msg)
                return SmsResult(sent=False, error=error_msg)

        except httpx.TimeoutException:
            error_msg = f"Brevo SMS timeout sending to {phone}"
            logger.error(error_msg)
            return SmsResult(sent=False, error=error_msg)
        except httpx.RequestError as exc:
            error_msg = f"Brevo SMS request failed: {type(exc).__name__}: {exc}"
            logger.error(error_msg)
            return SmsResult(sent=False, error=error_msg)
        except Exception as exc:
            error_msg = f"Brevo SMS unexpected error: {type(exc).__name__}: {exc}"
            logger.error(error_msg)
            return SmsResult(sent=False, error=error_msg)

    @staticmethod
    def _normalize_phone(phone: str) -> str | None:
        """Normalize phone number to international format."""
        if not phone:
            return None
        phone = phone.strip().replace(" ", "").replace("-", "")
        if phone.startswith("+"):
            return phone
        if phone.startswith("0"):
            # Convert local Nigerian to international
            return "+234" + phone[1:]
        if phone.startswith("234"):
            return "+" + phone
        return None


# Singleton provider instance
_provider: Optional[BrevoSmsProvider] = None
_provider_lock = threading.Lock()


def get_sms_provider() -> BrevoSmsProvider:
    """Get the singleton SMS provider instance."""
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = BrevoSmsProvider()
    return _provider


def send_sms(to: str, message: str, sender: str | None = None) -> SmsResult:
    """Convenience function to send SMS via the configured provider."""
    return get_sms_provider().send(to, message, sender)
