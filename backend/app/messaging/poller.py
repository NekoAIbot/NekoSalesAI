"""Telegram without a public URL.

The webhook in ``app.api.v1.routes.messaging`` needs Telegram to be able to reach
*in*: a public HTTPS address with a valid certificate. This box does not have one
and an ephemeral tunnel is not one either — a webhook pointed at a URL that
rotates is a bot that stops answering at an hour nobody chose.

``getUpdates`` inverts it. The process reaches *out*, holds the connection open
until Telegram has something, and gets it as the response. No inbound port, no
certificate, no tunnel, and it works from behind any NAT.

    python -m app.messaging.poller            # answer messages until stopped
    python -m app.messaging.poller --once     # drain what is waiting, then exit

**Telegram allows one delivery method at a time.** While a webhook is set,
``getUpdates`` returns 409 and this refuses to start. Removing the webhook is
therefore a decision about the *other* thing using that bot, not a detail — so it
is never done implicitly. ``scripts/telegram_setup.py --take-over`` does it, after
printing the URL it is about to displace.

The offset is what makes this exactly-once from Telegram's side: acknowledging
update N+1 is what stops N being redelivered. It is advanced only after handling,
so a crash mid-message replays it rather than losing it — and the duplicate is
then caught by ``InboundMessagingService``, which recognises a delivery it has
already answered. Two independent guards, because the failure they prevent is a
buyer being answered twice by an AI that appears not to remember saying it.
"""

from __future__ import annotations

import argparse
import signal
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config.logging import configure_logging, get_logger
from app.config.settings import settings
from app.database.session import SessionLocal
from app.messaging.inbound import parse_telegram_update
from app.messaging.service import InboundMessagingService, storefront_organization_id

logger = get_logger(__name__)

# How long Telegram holds the connection open waiting for something to happen.
# Long polling: 25 seconds of silence costs one request, not twenty-five.
LONG_POLL_SECONDS = 25

# Read timeout must exceed the long poll or every quiet period looks like a
# network failure.
READ_TIMEOUT = LONG_POLL_SECONDS + 10

# Only what the agent can act on. Telegram batches the rest and asking for less
# means less to discard — and, more usefully, means an update type added by a
# future Telegram release cannot arrive unannounced.
ALLOWED_UPDATES = ("message",)

# One 409 is a misconfiguration, not a blip: a webhook is set. Retrying would
# hammer the API and never succeed.
CONFLICT = 409


class PollerError(RuntimeError):
    """The poller cannot run, and no amount of retrying will change that."""


@dataclass
class PollReport:
    """What one drain did. Returned so a caller can assert on it."""

    updates: int = 0
    answered: int = 0
    ignored: int = 0
    duplicates: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.updates} updates, {self.answered} answered, "
            f"{self.ignored} ignored, {self.duplicates} duplicate, "
            f"{self.failed} failed"
        )


class TelegramPoller:
    """Pulls updates from Telegram and answers them.

    ``fetch`` is injectable for the same reason the clients' transport is: the
    interesting behaviour here is what happens to an awkward batch, and that
    should be testable without a bot, a token or a network.
    """

    def __init__(
        self,
        *,
        bot_token: str | None = None,
        base_url: str | None = None,
        fetch=None,
        session_factory=SessionLocal,
        service_factory=InboundMessagingService,
    ) -> None:
        self._token = bot_token if bot_token is not None else settings.TELEGRAM_BOT_TOKEN
        self._base = (base_url or settings.TELEGRAM_BASE_URL).rstrip("/")
        self._fetch = fetch or self._http_fetch
        self._session_factory = session_factory
        self._service_factory = service_factory

        # None means "whatever Telegram still considers unacknowledged", which is
        # the right thing to ask for on a cold start.
        self.offset: int | None = None
        self._stopping = False

    # ---------- the loop ----------

    def run(self, *, once: bool = False) -> PollReport:
        if not self._token:
            raise PollerError(
                "TELEGRAM_BOT_TOKEN is not set, so there is no bot to poll for."
            )

        total = PollReport()

        while True:
            report = self.drain()

            total.updates += report.updates
            total.answered += report.answered
            total.ignored += report.ignored
            total.duplicates += report.duplicates
            total.failed += report.failed
            total.errors.extend(report.errors)

            if once or self._stopping:
                return total

            # Nothing waiting and nothing to do: the next getUpdates blocks for
            # LONG_POLL_SECONDS, which is the sleep. No timer needed.

    def stop(self) -> None:
        """Finish the batch in hand, then return. Used by the signal handler."""
        self._stopping = True

    def drain(self) -> PollReport:
        """One getUpdates call, and every message in what came back."""
        report = PollReport()
        updates = self._get_updates()
        report.updates = len(updates)

        if not updates:
            return report

        db = self._session_factory()

        try:
            organization_id = storefront_organization_id(db)

            if organization_id is None:
                raise PollerError(
                    "No storefront organization in the database. Run the seed "
                    "first: there is no catalog to answer from."
                )

            service = self._service_factory(db)

            for update in updates:
                self._handle(service, db, organization_id, update, report)

                # After handling, never before. A crash between these two lines
                # replays the message; a crash after an early advance would lose
                # it silently, and a lost buyer question is worse than a repeated
                # answer that the dedupe guard will catch anyway.
                update_id = update.get("update_id")

                if isinstance(update_id, int):
                    self.offset = update_id + 1
        finally:
            db.close()

        logger.info("Telegram poll: %s", report.summary())

        return report

    def _handle(
        self,
        service: InboundMessagingService,
        db,
        organization_id: int,
        update: dict,
        report: PollReport,
    ) -> None:
        message = parse_telegram_update(update)

        if message is None:
            report.ignored += 1
            return

        try:
            handled = service.handle(organization_id, message)
        except Exception as exc:  # noqa: BLE001 - one bad update must not end the run
            db.rollback()
            report.failed += 1
            report.errors.append(f"{message.delivery_id}: {type(exc).__name__}: {exc}")
            logger.exception("Telegram update %s failed", message.delivery_id)
            return

        if handled.duplicate:
            report.duplicates += 1
            return

        service.deliver(message, handled.replies)
        report.answered += 1

    # ---------- talking to Telegram ----------

    def _get_updates(self) -> list[dict]:
        payload: dict[str, Any] = {
            "timeout": LONG_POLL_SECONDS,
            "allowed_updates": list(ALLOWED_UPDATES),
        }

        if self.offset is not None:
            payload["offset"] = self.offset

        body = self._fetch(payload)

        if not isinstance(body, dict) or not body.get("ok"):
            description = ""

            if isinstance(body, dict):
                description = str(body.get("description", ""))

            if "webhook" in description.lower():
                raise PollerError(
                    "Telegram is delivering to a webhook, so getUpdates is "
                    "refused. Remove it first — "
                    "python scripts/telegram_setup.py --take-over — which will "
                    "show you the URL it displaces before doing it."
                )

            logger.warning("getUpdates was refused: %s", description or body)
            return []

        result = body.get("result")

        return [item for item in result if isinstance(item, dict)] if isinstance(
            result, list
        ) else []

    def _http_fetch(self, payload: dict) -> Any:
        url = f"{self._base}/bot{self._token}/getUpdates"

        try:
            with httpx.Client(timeout=httpx.Timeout(READ_TIMEOUT, connect=10)) as client:
                response = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            # A dropped connection on a mobile link is ordinary. Returning
            # nothing means the loop tries again rather than dying on a blip.
            logger.warning("getUpdates could not reach Telegram: %s", exc)
            return {"ok": False, "description": str(exc)}

        if response.status_code == CONFLICT:
            raise PollerError(
                "Telegram returned 409: this bot has a webhook set, and a bot "
                "can have a webhook or be polled, not both. Run "
                "python scripts/telegram_setup.py --take-over to see the URL in "
                "place and remove it."
            )

        try:
            return response.json()
        except ValueError:
            logger.warning(
                "getUpdates returned non-JSON (%s)", response.status_code
            )
            return {"ok": False, "description": "non-JSON response"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Answer Telegram messages as Nera.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Drain what is waiting and exit, instead of running until stopped.",
    )
    args = parser.parse_args()

    configure_logging()

    poller = TelegramPoller()

    # Ctrl-C and a container stop both finish the message in hand first. Dropping
    # mid-message would leave a buyer's question answered in the transcript and
    # never sent.
    def _graceful(signum, _frame):
        logger.info("Signal %s received; finishing the current batch.", signum)
        poller.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _graceful)

    try:
        report = poller.run(once=args.once)
    except PollerError as exc:
        print(f"Cannot poll: {exc}")
        return 2

    print(report.summary())

    for error in report.errors:
        print(f"  failed: {error}")

    return 0 if not report.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
