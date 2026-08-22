"""Delivering one follow-up to every channel a customer chose.

``MailSender`` satisfied the ``Sender`` protocol for email alone. This replaces it
where a customer has picked more than one destination, and the interesting part is
what counts as success.

A follow-up is delivered if **at least one** chosen channel accepted it. That is
the useful definition: a customer who ticked email and WhatsApp has been told what
they needed to know once email lands, and holding the whole follow-up scheduled
because their WhatsApp number was stale would re-send the email on the next run
too. So partial success does not raise — it logs which channels failed and lets
the follow-up be marked sent.

Total failure raises ``FollowUpSendError``, which leaves the row scheduled for the
next run. The distinction is the whole reason this class exists rather than a loop
at the call site.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import mail
from app.config.logging import get_logger
from app.followups.service import Delivery, FollowUpSendError
from app.messaging.clients import (
    MessagingError,
    MessagingNotConfigured,
    TelegramClient,
    WhatsAppClient,
)
from app.models.workspace_profile import (
    CHANNEL_EMAIL,
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    WorkspaceProfile,
)

logger = get_logger(__name__)


@dataclass
class ChannelOutcome:
    channel: str
    sent: bool
    error: str | None = None


class FollowUpDispatcher:
    """Sends a follow-up on every channel the workspace can be reached on.

    The profile is passed at construction because channel preferences live on it,
    and ``FollowUpService`` already has the profile in hand when it decides to
    send. Passing it here keeps the ``Sender`` protocol unchanged.
    """

    def __init__(
        self,
        profile: WorkspaceProfile,
        telegram: TelegramClient | None = None,
        whatsapp: WhatsAppClient | None = None,
    ) -> None:
        self.profile = profile
        self.telegram = telegram or TelegramClient()
        self.whatsapp = whatsapp or WhatsAppClient()
        self.outcomes: list[ChannelOutcome] = []

    def send(self, delivery: Delivery) -> None:
        # reachable_channels, not chosen_channels: a customer can tick WhatsApp
        # before supplying a number, and attempting a channel with no destination
        # would report a failure for something they never finished setting up.
        channels = self.profile.reachable_channels
        self.outcomes = []

        for channel in channels:
            self.outcomes.append(self._send_one(channel, delivery))

        delivered = [o for o in self.outcomes if o.sent]
        failed = [o for o in self.outcomes if not o.sent]

        if failed:
            logger.warning(
                "Follow-up for workspace %s failed on %s",
                self.profile.id,
                ", ".join(f"{o.channel} ({o.error})" for o in failed),
            )

        if not delivered:
            reasons = "; ".join(f"{o.channel}: {o.error}" for o in self.outcomes)
            raise FollowUpSendError(
                f"No channel accepted this follow-up. {reasons}"
                if reasons
                else "No channel is configured for this workspace."
            )

    def _send_one(self, channel: str, delivery: Delivery) -> ChannelOutcome:
        try:
            if channel == CHANNEL_EMAIL:
                return self._send_email(delivery)
            if channel == CHANNEL_TELEGRAM:
                return self._send_telegram(delivery)
            if channel == CHANNEL_WHATSAPP:
                return self._send_whatsapp(delivery)
        except MessagingNotConfigured as exc:
            # A channel the deployment has no credentials for. Not the
            # customer's fault and not a broken send — reported so it shows up,
            # but it does not stop the others.
            return ChannelOutcome(channel, False, f"not configured: {exc}")
        except MessagingError as exc:
            return ChannelOutcome(channel, False, str(exc))
        except Exception as exc:  # noqa: BLE001 - one channel must not stop the rest
            logger.exception("Channel %s raised for workspace %s", channel, self.profile.id)
            return ChannelOutcome(channel, False, f"{type(exc).__name__}: {exc}")

        return ChannelOutcome(channel, False, "unknown channel")

    def _send_email(self, delivery: Delivery) -> ChannelOutcome:
        outcome = mail.send(
            mail.follow_up(
                to=delivery.to_email,
                subject=delivery.subject,
                body=delivery.body,
                workspace_profile_id=self.profile.id,
            )
        )

        return ChannelOutcome(CHANNEL_EMAIL, outcome.sent, outcome.error)

    def _send_telegram(self, delivery: Delivery) -> ChannelOutcome:
        chat_id = self.profile.telegram_chat_id

        if not chat_id:
            return ChannelOutcome(CHANNEL_TELEGRAM, False, "no chat id on file")

        # Subject and body joined, because Telegram has no subject line and
        # dropping it would lose the one-line summary the copy was written around.
        self.telegram.send_message(chat_id, f"{delivery.subject}\n\n{delivery.body}")

        return ChannelOutcome(CHANNEL_TELEGRAM, True)

    def _send_whatsapp(self, delivery: Delivery) -> ChannelOutcome:
        number = self.profile.whatsapp_number

        if not number:
            return ChannelOutcome(CHANNEL_WHATSAPP, False, "no number on file")

        self.whatsapp.send_message(number, f"{delivery.subject}\n\n{delivery.body}")

        return ChannelOutcome(CHANNEL_WHATSAPP, True)
