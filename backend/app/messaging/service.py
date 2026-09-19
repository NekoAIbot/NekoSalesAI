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
from app.messaging.config_flow import ConfigurationFlow, FlowResult
from app.messaging.inbound import (
    COMMAND_HELP,
    COMMAND_PAY,
    COMMAND_RESET,
    COMMAND_START,
    KIND_COMMAND,
    KIND_TEXT,
    KIND_UNSUPPORTED,
    InboundMessage,
)
from app.messaging.presentation import ChannelMessage, parse_callback, render_step
from app.sales.options import for_step
from app.models.channel_identity import (
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    ChannelIdentity,
)
from app.models.conversation import Conversation, Message
from app.products.config import ROLE_BUILDER
from app.products.resolver import resolve_config
from app.repositories.organization_repository import OrganizationRepository
from app.sales.closing import ClosingService
from app.sales.service import ConversationError, ConversationService
from app.sales.scoping import Scope

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

    ``channel_messages`` carries the same content as ``ChannelMessage``
    objects when interactive controls (Telegram inline keyboards, WhatsApp
    lists) are attached. The deliverer uses these in preference to the
    plain ``replies`` when present.
    """

    replies: list[str] = field(default_factory=list)
    conversation: Conversation | None = None
    duplicate: bool = False
    channel_messages: list = field(default_factory=list)


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
        self.closing = ClosingService(db)
        self._telegram = telegram
        self._whatsapp = whatsapp
        self.flow = ConfigurationFlow()

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

    def deliver(self, message: InboundMessage, replies: list[str], channel_messages: list | None = None) -> None:
        """Send the replies back on the channel they were asked on.

        ``channel_messages``, when present, carries the same content as
        ``ChannelMessage`` objects with interactive controls attached
        (Telegram inline keyboards, WhatsApp interactive lists). The
        deliverer uses these to call the channel-specific send methods;
        otherwise it falls back to plain ``send_message``.

        One failing message does not stop the next. A buyer receiving the
        second half of an answer is better served than one receiving nothing
        because the first half hit a rate limit.
        """
        client = self._client(message.channel)
        cms = channel_messages or []

        # Pair each reply with its ChannelMessage (if any) by index.
        for i, reply in enumerate(replies):
            if not reply.strip():
                continue

            cm = cms[i] if i < len(cms) else None

            try:
                if cm is not None:
                    self._send_with_controls(message.channel, client, message.external_id, reply, cm)
                else:
                    client.send_message(message.external_id, reply)
            except Exception:  # noqa: BLE001 - logged; the transcript is already right
                logger.exception(
                    "Could not deliver a reply on %s to %s",
                    message.channel,
                    message.external_id,
                )

    def _send_with_controls(
        self,
        channel: str,
        client,
        destination: str,
        text: str,
        cm,
    ) -> None:
        """Send a reply using channel-specific interactive controls."""
        if channel == CHANNEL_TELEGRAM and cm.telegram_inline_keyboard:
            client.send_message_with_keyboard(destination, text, cm.telegram_inline_keyboard)
        elif channel == CHANNEL_WHATSAPP and cm.whatsapp_list_rows:
            client.send_interactive_list(
                destination,
                text,
                cm.whatsapp_list_header,
                cm.whatsapp_list_button,
                cm.whatsapp_list_rows,
            )
        else:
            client.send_message(destination, text)

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
        # The interactive flow handles only explicit selections: Telegram
        # inline-keyboard callbacks ("scoping:products:sales_agent") and
        # WhatsApp numbered lists ("1", "1, 3"). Everything else — questions,
        # greetings, free-text answers — goes straight to the agent.
        scope = Scope.from_json(conversation.scope_json)
        flow_result: FlowResult | None = None

        step = scope.next_step
        if step is not None:
            options = for_step(step)
            if not options.free_text:
                text = message.text.strip()
                is_callback = parse_callback(text) is not None
                is_numbered = self.flow._is_numbered_selection(text, options)
                if is_callback or is_numbered:
                    flow_result = self.flow.handle_message(conversation, message, scope)

        if flow_result is not None and flow_result.replies:
            return Handled(
                replies=[rm.text for rm in flow_result.replies],
                channel_messages=flow_result.replies,
                conversation=conversation,
            )

        if flow_result is not None and flow_result.handled and not flow_result.selection_text:
            return Handled(replies=[], conversation=conversation)

        text = flow_result.selection_text if flow_result is not None else None
        agent_text = text if text is not None else message.text

        try:
            reply = self.conversations.handle_visitor_message(
                conversation,
                agent_text,
                external_id=message.delivery_id,
            )
        except ConversationError as exc:
            return Handled(replies=[str(exc)], conversation=conversation)

        replies = [reply.body] if reply.body.strip() else []
        channel_messages: list = []

        if replies:
            updated_scope = Scope.from_json(conversation.scope_json)
            step_msg = self.flow.present_step(updated_scope)
            if step_msg is not None:
                from app.messaging.presentation import ChannelMessage as _CM

                # Attach the keyboard/list to the last reply (the one that
                # ends on the selectable step). Greeting and other earlier
                # replies stay as plain text.
                cm = _CM(
                    text=replies[-1],
                    telegram_inline_keyboard=step_msg.telegram_inline_keyboard,
                    whatsapp_list_rows=step_msg.whatsapp_list_rows,
                    whatsapp_list_header=step_msg.whatsapp_list_header,
                    whatsapp_list_button=step_msg.whatsapp_list_button,
                )
                # Pad channel_messages so cm lands on the last reply index.
                channel_messages = [None] * (len(replies) - 1) + [cm]

            closed = self.closing.close(conversation)
            if closed is not None:
                replies.append(closed.message)

        return Handled(
            replies=replies,
            channel_messages=channel_messages,
            conversation=conversation,
        )

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

        if message.command == COMMAND_PAY:
            return self._payment_link(identity.conversation)

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

    def _payment_link(self, conversation: Conversation) -> Handled:
        """Answer "/pay": the link this thread has, or why there isn't one yet.

        The wording of a link and the wording of a refusal both come from
        ClosingService. What is decided here is only whether the buyer has got
        far enough to be asking a sensible question — and "not yet" is answered
        rather than ignored, because a buyer who types /pay and gets silence
        cannot tell a broken bot from a bot that is waiting on them.
        """
        closed = self.closing.resend(conversation)

        if closed is not None:
            return Handled(replies=[closed.message], conversation=conversation)

        return Handled(
            replies=[
                "There's nothing to pay for yet — we haven't settled on what "
                "you're buying. Tell me what your business needs and I'll price "
                "it, then /pay will bring up the link."
            ],
            conversation=conversation,
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
        """What this agent is, for someone who will not read a paragraph.

        Two texts, because there are two kinds of agent on this codebase and
        help that conflated them would be the same mistake in a new place. Nera
        is the *builder* — it makes the AI. What it builds is a *worker* — that
        is the AI that answers a business's buyers. Both can be reached over
        Telegram, so which one is answering decides which text is right.

        Written for an impatient reader: short lines, concrete verbs, the limits
        stated as plainly as the features.
        """
        config = resolve_config(self.db, identity.organization_id)

        if config.role == ROLE_BUILDER:
            return self._builder_help(config.agent_name)

        return self._worker_help(config)

    def _builder_help(self, name: str) -> str:
        """Nera's own help. The first line is the one that matters.

        An earlier version opened "an AI that sells for you", which described the
        thing Nera *makes* as though it were Nera — so a reader came away
        believing this chat was the AI that would answer their buyers. It isn't.
        A wrong first line here is not a wording problem: it sells the wrong
        product.

        Every line describes shipped code — pricing is
        ``app.pricing.complexity``, build-and-hand-over is
        ``app.payments.provisioning``, the approval gate is
        ``app.sales.approvals``, the reasoning trail is ``app.sales.reasoning``.
        Which is also why WHAT IT BUILDS names two AIs rather than twenty:
        advertising a capability before it works is the one thing that would make
        a product sold on "it won't overstate things" absurd.
        """
        return (
            f"{name} — the AI that builds AI for your business.\n"
            "─────────────────────\n"
            f"{name} doesn't sell for you. It builds the AI that does, and "
            "hands it over working.\n\n"
            "HOW IT GOES\n"
            "1. You say what your business needs done\n"
            f"2. {name} says which AI does it\n"
            "3. It prices the build — every line shown\n"
            "4. You pay, it builds, you get the keys\n\n"
            "WHAT IT BUILDS TODAY\n"
            "• AI Sales Representative — answers buyers, quotes your published "
            "prices, takes payment, follows up\n"
            "• AI Support Agent — answers from your own material, escalates "
            "anything commercial\n"
            "Ask for anything else and it says so plainly, then gets you a "
            "human. It won't pretend it can already ship it.\n\n"
            "WHERE WHAT IT BUILDS ANSWERS\n"
            "• Your website (a widget you paste in)\n"
            "• Telegram — a chat like this one\n"
            "• WhatsApp and email\n\n"
            "WHAT NEITHER WILL DO\n"
            "• Invent a price or a feature\n"
            "• Give a discount without approval\n"
            "• Guess — it hands the question to a person instead\n"
            "• Quote a build it can't deliver\n\n"
            "You see the reason behind every reply: what it read, which rule it "
            "followed, and the line it priced from.\n\n"
            "WANT ONE?\n"
            "Tell me what your business needs and I'll price the build.\n\n"
            "/pay — bring up your payment link again\n"
            "/reset — start over"
        )

    def _worker_help(self, config) -> str:
        """Help for an agent Nera built, answering its owner's buyers.

        Says less on purpose. This agent belongs to a business we do not speak
        for, so the only things stated are the ones the engine itself guarantees:
        it answers from what was published, and it fetches a person rather than
        guessing. Everything specific comes from the config.
        """
        name = config.agent_name
        who = config.company_name or "this business"
        can_sell = " what it costs," if config.sells_anything else ""

        return (
            f"{name} — the AI answering for {who}.\n"
            "─────────────────────\n"
            "WHAT I CAN DO\n"
            f"• Answer what {who} offers,{can_sell} day or night\n"
            "• Take your details so a person can follow up\n\n"
            "WHAT I WON'T DO\n"
            "• Invent a price or a promise\n"
            "• Guess — I hand the question to a person instead\n\n"
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
