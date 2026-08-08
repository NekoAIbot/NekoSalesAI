"""Paystack client.

Two calls are needed to sell something: initialize a transaction to get a
checkout URL, and verify one to find out whether it was actually paid. Both
are here, plus signature verification for the webhook.

Three deliberate choices:

1. The transport is injectable. Every caller can hand in a fake, so the entire
   checkout and provisioning flow is exercised in tests without a Paystack
   account, without network access, and without anyone's real key sitting in a
   fixture.

2. Amounts cross the boundary as integer minor units in both directions, and
   the amount Paystack reports back is compared against the order rather than
   trusted. A callback saying "paid" is a claim about money; it gets checked.

3. A missing key raises PaymentsNotConfigured rather than producing a request
   that will 401. The distinction matters at the call site: one is "this
   deployment has not been set up yet" and can be explained to a buyer, the
   other is "something is broken".
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config.logging import get_logger
from app.config.settings import settings

logger = get_logger(__name__)

# Paystack's own name for a successful charge.
PAYSTACK_SUCCESS = "success"


class PaymentsNotConfigured(RuntimeError):
    """No Paystack secret key is set, so checkout cannot be offered."""


class PaystackError(RuntimeError):
    """Paystack was reached but refused, or answered something unusable."""


@dataclass(frozen=True)
class Charge:
    """What Paystack says about one transaction."""

    reference: str
    status: str
    amount_minor: int
    currency: str
    paid: bool
    raw: dict[str, Any]


@dataclass(frozen=True)
class Checkout:
    """A payment link the buyer can be sent to."""

    reference: str
    authorization_url: str
    access_code: str


class Transport(Protocol):
    """The one method the client needs from the outside world."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        ...


class HttpxTransport:
    """The real one."""

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        response = httpx.request(
            method,
            url,
            headers=headers,
            json=json_body,
            timeout=self._timeout,
        )

        try:
            payload = response.json()
        except ValueError:
            # A gateway error page, usually. Surface the status rather than
            # letting a JSONDecodeError bubble up as a 500 with no context.
            raise PaystackError(
                f"Paystack returned {response.status_code} with a non-JSON body."
            )

        return response.status_code, payload


class PaystackClient:
    def __init__(
        self,
        secret_key: str | None = None,
        base_url: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        self._secret_key = (
            secret_key if secret_key is not None else settings.PAYSTACK_SECRET_KEY
        ).strip()
        self._base_url = (base_url or settings.PAYSTACK_BASE_URL).rstrip("/")
        self._transport = transport or HttpxTransport()

    @property
    def is_configured(self) -> bool:
        return bool(self._secret_key)

    def _headers(self) -> dict[str, str]:
        if not self._secret_key:
            raise PaymentsNotConfigured(
                "PAYSTACK_SECRET_KEY is not set, so no payment link can be created."
            )

        return {
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
        }

    def _call(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = self._headers()
        url = f"{self._base_url}{path}"

        status_code, payload = self._transport.request(
            method, url, headers=headers, json_body=json_body
        )

        if status_code >= 400 or not payload.get("status"):
            # Paystack puts the human-readable reason in "message" whether it
            # is a validation error or a rejected key.
            message = payload.get("message") or f"HTTP {status_code}"
            raise PaystackError(f"Paystack rejected the request: {message}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise PaystackError("Paystack response had no data object.")

        return data

    def initialize(
        self,
        *,
        email: str,
        amount_minor: int,
        currency: str,
        reference: str,
        callback_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> Checkout:
        """Create a transaction and return the URL to send the buyer to."""
        if amount_minor <= 0:
            raise PaystackError("Refusing to create a checkout for a non-positive amount.")

        data = self._call(
            "POST",
            "/transaction/initialize",
            {
                "email": email,
                "amount": amount_minor,
                "currency": currency,
                "reference": reference,
                "callback_url": callback_url,
                "metadata": metadata or {},
            },
        )

        url = data.get("authorization_url")
        if not url:
            raise PaystackError("Paystack did not return an authorization_url.")

        return Checkout(
            reference=str(data.get("reference") or reference),
            authorization_url=str(url),
            access_code=str(data.get("access_code") or ""),
        )

    def verify(self, reference: str) -> Charge:
        """Ask Paystack what actually happened to a transaction.

        This is the authority, not the browser callback. A buyer can navigate
        to the success URL without paying — the redirect is a hint that
        something finished, and this call is what decides whether it finished
        with money.
        """
        data = self._call("GET", f"/transaction/verify/{reference}")
        return self._to_charge(data, fallback_reference=reference)

    @staticmethod
    def _to_charge(data: dict[str, Any], fallback_reference: str = "") -> Charge:
        status = str(data.get("status") or "")

        try:
            amount_minor = int(data.get("amount") or 0)
        except (TypeError, ValueError):
            amount_minor = 0

        return Charge(
            reference=str(data.get("reference") or fallback_reference),
            status=status,
            amount_minor=amount_minor,
            currency=str(data.get("currency") or ""),
            paid=status == PAYSTACK_SUCCESS,
            raw=data,
        )

    def charge_from_webhook(self, event: dict[str, Any]) -> Charge | None:
        """Read a charge out of a webhook body, or None if it isn't one.

        Paystack sends many event types down the same URL. Anything that is
        not a successful charge is not our business here, and returning None
        keeps the caller from having to know the event taxonomy.
        """
        if event.get("event") != "charge.success":
            return None

        data = event.get("data")
        if not isinstance(data, dict):
            return None

        return self._to_charge(data)

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """Check the x-paystack-signature header against the raw body.

        HMAC-SHA512 of the *exact bytes received*, keyed with the secret key.
        Re-serialising the parsed JSON would change whitespace and key order
        and break the comparison, which is why the route hands us bytes.

        Compared with compare_digest so the check does not leak, through its
        own timing, how much of a forged signature was correct.
        """
        if not signature or not self._secret_key:
            return False

        expected = hmac.new(
            self._secret_key.encode("utf-8"),
            raw_body,
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)


def dump_payload(payload: dict[str, Any]) -> str:
    """Serialise a provider payload for storage, never raising on odd types."""
    try:
        return json.dumps(payload, default=str)[:20_000]
    except (TypeError, ValueError):
        return ""
