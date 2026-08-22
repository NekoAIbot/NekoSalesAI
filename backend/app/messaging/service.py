"""Nera, on Telegram and WhatsApp.

The parsing lives in ``app.messaging.inbound``; the selling lives, as it always
has, in ``app.sales.agent`` and ``app.sales.service``. This module is the join:
it remembers who a chat id is, hands their text to the same engine that answers
the website widget, and sends the reply back where it came from.

**Nothing here composes a reply.** Not one sentence of what a buyer is told about
the product is written in this file. That is the point — a messenger is a
different pipe, not a different agent, so a buyer who asks for 40% off on
WhatsApp gets the same refusal, the same escalation and the same approval row as
one who asks in the browser. Every string that *is* here (the help text, the note
about photos) is about the pipe itself, and says nothing about prices, plans or
terms.

Two things a messenger has that a browser does not:

*Retries.* Both platforms deliver at least once and will re-send anything they do
not see acknowledged. So each delivery is recorded against the turn it produced,
and a second copy is dropped rather than answered twice.

*Commands.* Telegram sends ``/start`` on the buyer's behalf before they have
typed anything. Forwarded to the agent it would look like a buyer opening with a
slash, so the handful of conventions people expect are handled here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.config.settings import settings
from app.messaging.clients import TelegramClient, WhatsAppClient
from app.messaging.inbound import (
    COMMAND_HELP,
    COMMAND_RESET,
    COMMAND_START,
    KIND_COMMAND,
    KIND_TEXT,
    KIND_UNSUPPORTED,
    InboundMessage,
)
from app.models.channel_identity import (
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    ChannelIdentity,
)
from app.models.conversation import Conversation, Message
from app.products.resolver import resolve_config
from app.repositories.organization_repository import OrganizationRepository
from app.sales.service import ConversationError, ConversationService

logger = get_logger(__name__)


def storefront_organization_id(db: Session) -> int | None:
    """Whose agent answers the deployment's own bot.

    There is one ``TELEGRAM_BOT_TOKEN`` and one ``WHATSAPP_PHONE_NUMBER_ID`` per
    deployment, and they belong to whoever runs it — so a message arriving on
    them is a message to the storefront's own agent, selling the storefront's own
    product. That is the whole of the routing today.

    A customer wanting *their* agent on Telegram needs their own bot, because a
    bot is a Telegram account and two catalogs cannot share one. When that
    arrives it becomes a lookup by bot id and nothing else here changes, which is
    why ``ChannelIdentity`` is already keyed by organization.

    Returns None on a database with no storefront — a fresh clone that was never
    seeded. The callers drop the message and log, rather than opening a
    conversation against an organization that does not exist.
    """
    org = OrganizationRepository(db).get_by_slug(settings.STOREFRONT_ORG_SLUG)

    return org.id if org else None


@dataclass
class Handled:
    """What one delivery came to.

    ``replies`` is what to send, in order. Empty is a real outcome, not a
    failure: a duplicate delivery, or a thread a human has taken over.
    """

    replies: list[str] = field(default_factory=list)
    conversation: Conversation | None = None
    duplicate: bool = False


class InboundMessagingService:
    """Runs one inbound message through the sales agent and answers it."""

    def __init__(
        self,
        db: Session,
        telegram: TelegramClient | None = None,
        whatsapp: WhatsAppClient | None = None,
    ) -> None:
        self.db = db
        self.conversations = ConversationService(db)
        self._telegram = telegram
        self._whatsapp = whatsapp

    # ---------- the two halves ----------

    def handle(self, organization_id: int, message: InboundMessage) -> Handled:
        """Decide what to say. Sends nothing."""
        identity = self._identity(organization_id, message)

        if identity is not None and self._already_handled(identity, message):
            logger.info(
                "Dropping duplicate %s delivery %s",
                message.channel,
                message.delivery_id,
            )
            return Handled(duplicate=True, conversation=identity.conversation)

        if identity is None:
            identity, opening = self._open_thread(organization_id, message)
            greeting = [opening] if opening else []
        else:
            greeting = []

        identity.last_seen_at = datetime.now(timezone.utc)

        if message.sender_name and not identity.display_name:
            identity.display_name = message.sender_name

        handled = self._respond_to(identity, message)

        if greeting and handled.replies and handled.replies[0].strip() == greeting[0].strip():
            # The buyer opened with "hi", and the agent's answer to a greeting
            # *is* the greeting — so first contact would send the same paragraph
            # twice in a row. On a messenger that reads as a broken bot, and it
            # is the very first thing a buyer sees. Only a browser visitor is
            # spared it, because there the greeting is already on screen before
            # they type.
            handled.replies = greeting
        else:
            handled.replies = greeting + handled.replies

        # Recorded last, against whichever turn this delivery produced, so a
        # retry that arrives after a crash mid-handling is *not* suppressed —
        # the buyer would rather be answered twice than never.
        self._record_delivery(identity.conversation_id, message.delivery_id)
        self.db.commit()

        return handled

    def deliver(self, message: InboundMessage, replies: list[str]) -> None:
        """Send the replies back on the channel they were asked on.

        One failing message does not stop the next. A buyer receiving the second
        half of an answer is better served than one receiving nothing because the
        first half hit a rate limit.
        """
        for reply in replies:
            if not reply.strip():
                continue

            try:
                self._client(message.channel).send_message(
                    message.external_id, reply
                )
            except Exception:  # noqa: BLE001 - logged; the transcript is already right
                logger.exception(
                    "Could not deliver a reply on %s to %s",
                    message.channel,
                    message.external_id,
                )

    # ---------- identity ----------

    def _identity(
        self,
        organization_id: int,
        message: InboundMessage,
    ) -> ChannelIdentity | None:
        return self.db.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.organization_id == organization_id,
                ChannelIdentity.channel == message.channel,
                ChannelIdentity.external_id == message.external_id,
            )
        ).scalars().first()

    def _open_thread(
        self,
        organization_id: int,
        message: InboundMessage,
    ) -> tuple[ChannelIdentity, str]:
        """First contact: a conversation, a mapping to it, and the greeting."""
        conversation = self.conversations.start(organization_id)

        if message.sender_name:
            conversation.visitor_name = message.sender_name

        identity = ChannelIdentity(
            organization_id=organization_id,
            channel=message.channel,
            external_id=message.external_id,
            conversation_id=conversation.id,
            display_name=message.sender_name,
        )

        self.db.add(identity)
        self.db.commit()
        self.db.refresh(identity)

        return identity, self._opening_line(conversation)

    def _opening_line(self, conversation: Conversation) -> str:
        """The greeting ``ConversationService.start`` already stored.

        Read back rather than recomposed: the transcript a human reviews and the
        message the buyer received have to be the same words, and there is only
        one place those words come from.
        """
        stored = self.conversations.messages(conversation.id)

        return stored[0].body if stored else ""

    def _new_thread_for(self, identity: ChannelIdentity) -> str:
        """Point an existing identity at a fresh conversation."""
        conversation = self.conversations.start(identity.organization_id)

        if identity.display_name:
            conversation.visitor_name = identity.display_name

        identity.conversation_id = conversation.id
        self.db.commit()
        self.db.refresh(identity)

        return self._opening_line(conversation)

    # ---------- responding ----------

    def _respond_to(
        self,
        identity: ChannelIdentity,
        message: InboundMessage,
    ) -> Handled:
        conversation = identity.conversation

        if message.kind == KIND_UNSUPPORTED:
            return Handled(replies=[self._cannot_read(message)], conversation=conversation)

        if message.kind == KIND_COMMAND:
            return self._run_command(identity, message)

        if message.kind != KIND_TEXT:
            return Handled(conversation=conversation)

        return self._ask_the_agent(conversation, message)

    def _ask_the_agent(
        self,
        conversation: Conversation,
        message: InboundMessage,
    ) -> Handled:
        try:
            reply = self.conversations.handle_visitor_message(
                conversation,
                message.text,
                external_id=message.delivery_id,
            )
        except ConversationError as exc:
            # Too long, or empty after stripping. The limit is the agent's, so
            # the explanation is too — repeating it here is the only way the
            # buyer learns why nothing happened.
            return Handled(replies=[str(exc)], conversation=conversation)

        # An empty body means a human has the thread and the agent stayed quiet.
        # Sending anything at all would be the AI talking over its colleague.
        replies = [reply.body] if reply.body.strip() else []

        return Handled(replies=replies, conversation=conversation)

    def _run_command(
        self,
        identity: ChannelIdentity,
        message: InboundMessage,
    ) -> Handled:
        if message.command == COMMAND_START:
            return Handled(
                replies=[self._opening_line(identity.conversation)],
                conversation=identity.conversation,
            )

        if message.command == COMMAND_RESET:
            return Handled(
                replies=[self._new_thread_for(identity)],
                conversation=identity.conversation,
            )

        if message.command == COMMAND_HELP:
            return Handled(
                replies=[self._help_text(identity)],
                conversation=identity.conversation,
            )

        # Anything else — "/pricing", "/plans" — is a buyer asking a question
        # with a slash in front of it. The agent reads the words; refusing on
        # the punctuation would be pedantry.
        stripped = message.text.lstrip("/").strip()

        if not stripped:
            return Handled(
                replies=[self._help_text(identity)],
                conversation=identity.conversation,
            )

        return self._ask_the_agent(
            identity.conversation,
            InboundMessage(
                channel=message.channel,
                external_id=message.external_id,
                delivery_id=message.delivery_id,
                kind=KIND_TEXT,
                text=stripped,
                sender_name=message.sender_name,
            ),
        )

    # ---------- the few strings that belong to the pipe ----------

    def _agent_name(self, identity: ChannelIdentity) -> str:
        """Whose agent this is, from the config that will answer.

        Not a constant: on a customer's own catalog the agent has the customer's
        chosen name, and a help text calling it Nera would be wrong.
        """
        return resolve_config(self.db, identity.organization_id).agent_name

    def _cannot_read(self, message: InboundMessage) -> str:
        thing = message.media_kind or "that"

        return (
            f"I can only read text — I can't open a {thing}. "
            "Type your question and I'll answer it."
        )

    def _help_text(self, identity: ChannelIdentity) -> str:
        """What Nera is, for someone who will not read a paragraph.

        Written for an impatient reader: short lines, concrete verbs, the limits
        stated as plainly as the features. Every line describes something that
        exists in shipped code today — the price list comes from the same config
        the agent answers from, the approval gate is ``app.sales.approvals``, the
        reasoning log is ``app.sales.reasoning``. Nothing here is a roadmap.
        Advertising a capability before it works is the one thing that would make
        a product sold on "it won't overstate things" absurd.
        """
        name = self._agent_name(identity)

        return (
            f"{name} — an AI that sells for you.\n"
            "─────────────────────\n"
            "WHAT IT DOES\n"
            "• Answers buyers about what you sell, day or night\n"
            "• Quotes only prices you've published — itemised\n"
            "• Qualifies, captures the lead, takes payment\n"
            "• Follows up if they go quiet\n\n"
            "WHERE IT WORKS\n"
            "• Your website (a widget you paste in)\n"
            "• Telegram — this chat\n"
            "• WhatsApp and email\n\n"
            "WHAT IT WON'T DO\n"
            "• Invent a price or a feature\n"
            "• Give a discount without your approval\n"
            "• Guess — it hands the question to a person instead\n\n"
            "You see the reason behind every reply: what it read, which rule it "
            "followed, and the price list line it quoted.\n\n"
            "WANT ONE?\n"
            "Tell me what your business sells and I'll price it.\n\n"
            "/reset — start over"
        )

    # ---------- plumbing ----------

    def _client(self, channel: str):
        if channel == CHANNEL_TELEGRAM:
            if self._telegram is None:
                self._telegram = TelegramClient()
            return self._telegram

        if channel == CHANNEL_WHATSAPP:
            if self._whatsapp is None:
                self._whatsapp = WhatsAppClient()
            return self._whatsapp

        raise ValueError(f"No client for channel {channel!r}.")

    def _already_handled(
        self,
        identity: ChannelIdentity,
        message: InboundMessage,
    ) -> bool:
        return (
            self.db.execute(
                select(Message.id).where(
                    Message.conversation_id == identity.conversation_id,
                    Message.external_id == message.delivery_id,
                )
            ).scalars().first()
            is not None
        )

    def _record_delivery(self, conversation_id: int, delivery_id: str) -> None:
        """Stamp the newest turn in the thread with the delivery that caused it.

        Whichever turn that is — a greeting, an answer, a note about a sticker —
        it is the row ``_already_handled`` will find if the platform sends the
        same delivery again.
        """
        newest = self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(1)
        ).scalars().first()

        if newest is not None and newest.external_id is None:
            newest.external_id = delivery_id
