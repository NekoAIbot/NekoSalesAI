"""Sending email.

Nothing in this project could send a message before this module. Receipts were
promised on the landing page and never sent, the one-time admin password was
shown on screen and nowhere else, and the six post-sale follow-ups were written,
scheduled, and then only ever displayed in the desk for a human to act on. The
follow-up loop was a calendar nobody rang.

Three backends, chosen by ``MAIL_BACKEND``:

``console`` (default) logs the message instead of sending it. That is the right
default for this project, not a placeholder: a fresh clone with no credentials
runs the whole purchase flow end to end and shows what *would* have been sent,
and no test can quietly post to the internet.

``smtp`` sends for real.

``memory`` keeps messages in a list for tests to assert on.

The transport takes a fully-composed message and does not know what a receipt
is. Content lives in ``app.mail.messages``, so a change to what an email says is
never a change to how it is delivered.

Failure is reported, never raised at the caller by default. A provisioning that
rolled back because a receipt could not be sent would turn a delivery problem
into a customer who paid and got nothing — the money has already moved by then,
so the workspace matters more than the notification.
"""

from __future__ import annotations

import smtplib
import threading
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr

from app.config.logging import get_logger
from app.config.settings import settings

logger = get_logger(__name__)

BACKEND_CONSOLE = "console"
BACKEND_SMTP = "smtp"
BACKEND_MEMORY = "memory"
BACKEND_BREVO = "brevo"


@dataclass(frozen=True)
class Message:
    """One email, composed and ready to send."""

    to: str
    subject: str
    body: str

    # Set when the message is about a specific workspace, so a failed send can
    # be traced back to the customer it concerned.
    workspace_profile_id: int | None = None

    def __post_init__(self) -> None:
        if not self.to or "@" not in self.to:
            raise ValueError(f"Not a sendable address: {self.to!r}")
        if not self.subject.strip():
            raise ValueError("An email needs a subject.")


@dataclass
class SendResult:
    """Whether a message went out, and why not if it did not."""

    sent: bool
    backend: str
    error: str | None = None


import time
import uuid
from typing import Literal

DeliveryState = Literal["queued", "accepted", "delivered", "failed"]

@dataclass
class DeliveryRecord:
    """Observability record distinguishing queued, accepted, delivered, and failed states."""
    delivery_id: str
    to: str
    subject: str
    state: DeliveryState
    created_at: float
    completed_at: float | None = None
    backend: str = ""
    error: str | None = None

_delivery_history: list[DeliveryRecord] = []
_delivery_history_lock = threading.Lock()
MAX_DELIVERY_HISTORY = 100

def get_delivery_history(limit: int = 50) -> list[DeliveryRecord]:
    with _delivery_history_lock:
        return list(_delivery_history[-limit:])

def record_delivery_event(
    delivery_id: str,
    to: str,
    subject: str,
    state: DeliveryState,
    backend: str = "",
    error: str | None = None,
) -> DeliveryRecord:
    with _delivery_history_lock:
        for rec in _delivery_history:
            if rec.delivery_id == delivery_id:
                rec.state = state
                if backend:
                    rec.backend = backend
                if error:
                    rec.error = error
                if state in ("delivered", "failed"):
                    rec.completed_at = time.time()
                return rec
        rec = DeliveryRecord(
            delivery_id=delivery_id,
            to=to,
            subject=subject,
            state=state,
            created_at=time.time(),
            backend=backend,
            error=error,
        )
        _delivery_history.append(rec)
        if len(_delivery_history) > MAX_DELIVERY_HISTORY:
            del _delivery_history[: len(_delivery_history) - MAX_DELIVERY_HISTORY]
        return rec

class MailTransport:
    """Base class. Subclasses implement ``_deliver``."""

    name = "base"

    def send(self, message: Message, delivery_id: str | None = None) -> SendResult:
        if delivery_id:
            record_delivery_event(delivery_id, message.to, message.subject, "accepted", backend=self.name)
        try:
            self._deliver(message)
        except Exception as exc:  # noqa: BLE001 - reported, not propagated
            # Logged with the address so a bounce can be chased, and with the
            # exception type so a credential problem is distinguishable from a
            # network one.
            logger.error(
                "Email to %s failed via %s: %s: %s",
                message.to,
                self.name,
                type(exc).__name__,
                exc,
            )
            if delivery_id:
                record_delivery_event(delivery_id, message.to, message.subject, "failed", backend=self.name, error=str(exc))
            return SendResult(sent=False, backend=self.name, error=str(exc))

        if delivery_id:
            record_delivery_event(delivery_id, message.to, message.subject, "delivered", backend=self.name)
        return SendResult(sent=True, backend=self.name)

    def _deliver(self, message: Message) -> None:
        raise NotImplementedError


class ConsoleMailTransport(MailTransport):
    """Logs instead of sending.

    The default, so a clone with no SMTP credentials still exercises every path
    that sends mail and shows the operator exactly what a customer would have
    received.
    """

    name = BACKEND_CONSOLE

    def _deliver(self, message: Message) -> None:
        logger.info(
            "[mail:console] to=%s subject=%s\n%s",
            message.to,
            message.subject,
            message.body,
        )


class MemoryMailTransport(MailTransport):
    """Keeps messages in memory for tests to assert on."""

    name = BACKEND_MEMORY

    def __init__(self) -> None:
        self.outbox: list[Message] = []
        self._lock = threading.Lock()

    def _deliver(self, message: Message) -> None:
        with self._lock:
            self.outbox.append(message)

    def clear(self) -> None:
        with self._lock:
            self.outbox.clear()


class BrevoApiMailTransport(MailTransport):
    """Sends via Brevo v3 Transactional Email REST API."""

    name = BACKEND_BREVO

    def _deliver(self, message: Message) -> None:
        if not settings.BREVO_API_KEY:
            raise RuntimeError("MAIL_BACKEND is brevo but BREVO_API_KEY is not set.")

        import httpx
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": settings.BREVO_API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        }
        payload = {
            "sender": {
                "name": settings.MAIL_FROM_NAME,
                "email": settings.MAIL_FROM,
            },
            "to": [{"email": message.to}],
            "subject": message.subject,
            "textContent": message.body,
        }
        res = httpx.post(url, headers=headers, json=payload, timeout=settings.SMTP_TIMEOUT)
        if res.status_code >= 400:
            try:
                data = res.json()
                error_msg = data.get("message", res.text)
            except Exception:
                error_msg = f"HTTP {res.status_code}"
            # Never leak api keys in logs or errors
            if settings.BREVO_API_KEY and settings.BREVO_API_KEY in error_msg:
                error_msg = error_msg.replace(settings.BREVO_API_KEY, "[REDACTED]")
            raise RuntimeError(f"Brevo API returned error ({res.status_code}): {error_msg}")


class SmtpMailTransport(MailTransport):
    """Sends over SMTP with automatic port fallback (587 -> 2525).

    Works with any SMTP provider: Brevo, Mailjet, SendGrid, Amazon SES,
    Gmail, etc. Configuration is entirely environment-based so the same
    binary runs in development (console) and production (smtp) without
    code changes.
    """

    name = BACKEND_SMTP

    def _connect(self, port: int) -> smtplib.SMTP | smtplib.SMTP_SSL:
        if settings.SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(
                settings.SMTP_HOST, port, timeout=settings.SMTP_TIMEOUT
            )
        else:
            server = smtplib.SMTP(
                settings.SMTP_HOST, port, timeout=settings.SMTP_TIMEOUT
            )

        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            server.starttls()

        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

        return server

    def _deliver(self, message: Message) -> None:
        if not settings.SMTP_HOST:
            raise RuntimeError("MAIL_BACKEND is smtp but SMTP_HOST is not set.")

        email = EmailMessage()
        email["To"] = message.to
        email["From"] = formataddr((settings.MAIL_FROM_NAME, settings.MAIL_FROM))
        email["Subject"] = message.subject
        email.set_content(message.body)

        primary_port = settings.SMTP_PORT or 2525
        fallback_port = 587 if primary_port == 2525 else 2525

        server = None
        try:
            server = self._connect(primary_port)
            server.send_message(email)
        except (TimeoutError, smtplib.SMTPConnectError, OSError) as exc:
            logger.warning(
                "Primary SMTP port %d failed (%s); trying fallback port %d.",
                primary_port,
                exc,
                fallback_port,
            )
            try:
                server = self._connect(fallback_port)
                server.send_message(email)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"SMTP delivery failed on both ports {primary_port} and {fallback_port}: {fallback_exc}"
                ) from fallback_exc
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass


# One transport per process. Built on first use rather than at import, so tests
# can install a memory transport before anything sends.
_transport: MailTransport | None = None
_transport_lock = threading.Lock()


def build_transport(backend: str | None = None) -> MailTransport:
    chosen = (backend or settings.MAIL_BACKEND or BACKEND_CONSOLE).strip().lower()

    if chosen == BACKEND_SMTP:
        return SmtpMailTransport()
    if chosen in (BACKEND_BREVO, "brevo_api"):
        return BrevoApiMailTransport()
    if chosen == BACKEND_MEMORY:
        return MemoryMailTransport()
    if chosen != BACKEND_CONSOLE:
        logger.warning(
            "Unknown MAIL_BACKEND %r, falling back to %s.", chosen, BACKEND_CONSOLE
        )

    return ConsoleMailTransport()


def get_transport() -> MailTransport:
    global _transport

    if _transport is None:
        with _transport_lock:
            if _transport is None:
                _transport = build_transport()

    return _transport


def set_transport(transport: MailTransport | None) -> None:
    """Install a transport, or reset to the configured one with ``None``."""
    global _transport
    with _transport_lock:
        _transport = transport


def send(message: Message, delivery_id: str | None = None) -> SendResult:
    return get_transport().send(message, delivery_id=delivery_id)


def send_in_background(message: Message) -> threading.Thread:
    """Dispatch sending to a background daemon thread so HTTP requests never block.
    
    Surfaces delivery state (queued -> accepted -> delivered / failed) in the
    in-memory delivery tracker so errors are never silently swallowed.
    """
    delivery_id = f"dlv_{uuid.uuid4().hex[:12]}"
    record_delivery_event(delivery_id, message.to, message.subject, "queued")

    def _runner():
        send(message, delivery_id=delivery_id)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.delivery_id = delivery_id  # type: ignore[attr-defined]
    thread.start()
    return thread
