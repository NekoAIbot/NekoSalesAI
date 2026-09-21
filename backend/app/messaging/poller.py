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
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import build
from app.config.logging import configure_logging, get_logger
from app.config.settings import settings
from app.database.session import SessionLocal
from app.messaging.clients import TelegramClient, WhatsAppClient
from app.messaging.inbound import parse_telegram_update
from app.messaging.service import InboundMessagingService, storefront_organization_id
from app.payments.delivery import DeliveryPusher, DeliveryReport, DeliveryService

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
ALLOWED_UPDATES = ("message", "callback_query")

# One 409 is a misconfiguration, not a blip: a webhook is set. Retrying would
# hammer the API and never succeed.
CONFLICT = 409

# Backoff for a getUpdates that never reached Telegram. Starts at a second
# because most outages here are a phone changing masts, and caps at half a minute
# because a buyer who messaged during the outage is waiting behind it.
FAILURE_BACKOFF_BASE = 1
FAILURE_BACKOFF_MAX = 30

# A sustained outage must not write a line per retry. The first failure is logged
# and then every tenth, so the log records the outage without becoming it.
QUIET_AFTER = 10


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
        push_clients=None,
    ) -> None:
        self._token = bot_token if bot_token is not None else settings.TELEGRAM_BOT_TOKEN
        self._base = (base_url or settings.TELEGRAM_BASE_URL).rstrip("/")
        self._fetch = fetch or self._http_fetch
        self._session_factory = session_factory
        self._service_factory = service_factory

        # Where a post-payment message goes out. Injectable for the same reason
        # ``fetch`` is: delivering a paid order is the most consequential thing
        # this process does, and it has to be testable without a real bot token
        # pointed at a real buyer.
        self._pusher = DeliveryPusher(
            push_clients
            if push_clients is not None
            else {
                "telegram": TelegramClient(bot_token=bot_token),
                "whatsapp": WhatsAppClient(),
            }
        )

        # None means "whatever Telegram still considers unacknowledged", which is
        # the right thing to ask for on a cold start.
        self.offset: int | None = None
        self._stopping = False

        # Whether the last getUpdates actually reached Telegram, and how many in
        # a row have not. See the backoff in ``run``.
        self._failures = 0

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

            # Payments, every cycle, whether or not anybody messaged.
            #
            # Outside drain() on purpose. drain() returns early when Telegram had
            # nothing, and a payment arrives with no Telegram update attached to
            # it — a buyer taps the checkout link, pays in Paystack's tab, and
            # sends no further message at all. Reconciling inside drain() would
            # mean the quieter the thread, the longer the buyer waits, which is
            # exactly backwards.
            self.reconcile_payments()

            if once or self._stopping:
                return total

            # A successful poll needs no timer: getUpdates held the connection
            # open for LONG_POLL_SECONDS, and that *was* the sleep.
            #
            # A failed one is the opposite. A DNS failure on a dropped uplink
            # comes back instantly, so this loop used to spin as fast as
            # resolution could fail — one and a quarter million log lines, and on
            # a phone, the battery. The long poll being the sleep was true right
            # up until the request stopped being made.
            self._wait_after_failure()

    def _wait_after_failure(self) -> None:
        """Back off while Telegram is unreachable, and not otherwise.

        Doubling, capped. The cap matters more than the curve: an uplink that
        comes back should be noticed in under a minute, because the buyer who
        messaged during the outage is waiting on the other side of it.
        """
        if not self._failures:
            return

        delay = min(FAILURE_BACKOFF_MAX, FAILURE_BACKOFF_BASE * 2 ** (self._failures - 1))

        if self._failures == 1 or self._failures % QUIET_AFTER == 0:
            logger.info(
                "Telegram unreachable (%s in a row); waiting %ss before retrying.",
                self._failures,
                delay,
            )

        # Interruptible, so a SIGTERM during an outage does not have to wait out
        # the whole backoff before the process can exit.
        waited = 0.0
        while waited < delay and not self._stopping:
            time.sleep(min(1.0, delay - waited))
            waited += 1.0

    def stop(self) -> None:
        """Finish the batch in hand, then return. Used by the signal handler."""
        self._stopping = True

    # ---------- payments ----------

    def reconcile_payments(self) -> DeliveryReport:
        """Turn confirmed payments into something the buyer can see.

        This process is where reconciliation lives because it is the only one
        that runs on its own. The web server acts when a browser asks it to, and
        a buyer who paid from a chat has no browser in the loop — which is how a
        real ₦148,000 order came to be paid, provisioned and emailed while the
        person who paid for it heard nothing in the thread they were watching.

        Never raises. A payment problem must not stop the bot answering
        messages, and a reconcile that throws inside the poll loop would take the
        whole process down and cost every buyer, not just the one whose order
        failed.
        """
        db = self._session_factory()

        try:
            report = DeliveryService(db).reconcile()
        except Exception:
            logger.exception("Payment reconcile failed")
            return DeliveryReport(errors=["reconcile raised"])
        finally:
            db.close()

        self._pusher.send_all(report.pushes)

        if not report.quiet:
            logger.info("Payment reconcile: %s", report.summary())

        for error in report.errors:
            logger.warning("Payment reconcile: %s", error)

        return report

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

        # A callback query is acknowledged immediately, before the reply is
        # composed: it stops the button's loading spinner on the buyer's
        # screen at once, and the actual answer follows as the edited message
        # or a new one. The selection itself is already recorded — the
        # acknowledgement is purely cosmetic, so its failure is harmless.
        if message.callback_message_id is not None:
            query_id = message.delivery_id.removeprefix("tgcb:")
            self._answer_callback(query_id)

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

        service.deliver(message, handled.replies, handled.channel_messages)
        report.answered += 1

    def _answer_callback(self, query_id: str) -> None:
        """Acknowledge a button press. Never raises."""
        try:
            TelegramClient(bot_token=self._token).answer_callback_query(query_id)
        except Exception:  # noqa: BLE001 - cosmetic; the answer still goes out
            pass

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
            self._failures += 1
            return []

        self._failures = 0

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

    # First line in the log, every start. "Is the live process running current
    # code?" is the question that cost the most time on this project, and it is
    # unanswerable after the fact: a poller that never crashes never reloads, and
    # nothing in the log distinguishes it from one started a minute ago. Now it
    # does, and the answer sits above whatever the process goes on to do.
    logger.info("Poller starting — %s", build.describe())

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
