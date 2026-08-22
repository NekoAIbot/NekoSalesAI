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


class MailTransport:
    """Base class. Subclasses implement ``_deliver``."""

    name = "base"

    def send(self, message: Message) -> SendResult:
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
            return SendResult(sent=False, backend=self.name, error=str(exc))

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


class SmtpMailTransport(MailTransport):
    """Sends over SMTP."""

    name = BACKEND_SMTP

    def _deliver(self, message: Message) -> None:
        if not settings.SMTP_HOST:
            raise RuntimeError("MAIL_BACKEND is smtp but SMTP_HOST is not set.")

        email = EmailMessage()
        email["To"] = message.to
        email["From"] = formataddr((settings.MAIL_FROM_NAME, settings.MAIL_FROM))
        email["Subject"] = message.subject
        email.set_content(message.body)

        if settings.SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT
            )
        else:
            server = smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT
            )

        with server:
            if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
                server.starttls()

            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

            server.send_message(email)


# One transport per process. Built on first use rather than at import, so tests
# can install a memory transport before anything sends.
_transport: MailTransport | None = None
_transport_lock = threading.Lock()


def build_transport(backend: str | None = None) -> MailTransport:
    chosen = (backend or settings.MAIL_BACKEND or BACKEND_CONSOLE).strip().lower()

    if chosen == BACKEND_SMTP:
        return SmtpMailTransport()
    if chosen == BACKEND_MEMORY:
        return MemoryMailTransport()
    if chosen != BACKEND_CONSOLE:
        # An unrecognised backend logs and falls back rather than failing to
        # start: a typo in an env var should not take the whole app down, and
        # console loses nothing but the delivery.
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


def send(message: Message) -> SendResult:
    return get_transport().send(message)
