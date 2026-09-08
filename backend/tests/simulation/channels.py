"""The same conversation, driven through three different front doors.

Cross-platform consistency cannot be checked by writing three test suites; they
drift, and the drift *is* the bug. So there is one conversation script and three
adapters, each ending in the same place — ``ConversationService`` — by the same
route production uses:

``WebSurface``       real HTTP, through the storefront routes a browser calls.
``TelegramSurface``  a real Telegram update dict, parsed by the real parser, run
                     through ``InboundMessagingService``.
``WhatsAppSurface``  the same, with WhatsApp's very different payload shape.

The adapters are deliberately thin and deliberately *not* shortcuts. Telegram
does not call ``handle_visitor_message`` directly, because the bug that started
this — "Done" escalating to a human — lived in the messaging layer's command and
duplicate handling, above the engine. A simulation that skipped that layer would
have reported everything healthy.

Each turn is read back from the database rather than from the reply text. The
rule name is the machine-checkable fact; the prose is rephrased and must never
be what a test depends on.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.messaging.inbound import KIND_COMMAND, KIND_TEXT, InboundMessage
from app.messaging.service import InboundMessagingService, storefront_organization_id
from app.models.channel_identity import CHANNEL_TELEGRAM, CHANNEL_WHATSAPP
from app.models.conversation import ROLE_AGENT, Conversation, Message
from app.sales.reasoning import Reasoning


@dataclass
class Turn:
    """One exchange, in the only shape the checks look at."""

    said: str
    replies: list[str]
    rule: str | None
    escalated: bool
    stage: str | None
    signals: list[str]

    @property
    def text(self) -> str:
        return "\n\n".join(self.replies)


def _reasoning_of(db: Session, conversation_id: int) -> tuple[str | None, bool, list]:
    """The rule behind the newest agent turn.

    Read from the row rather than returned from the call because the three
    surfaces return three different things — an HTTP body, a ``Handled``, a
    ``Message`` — and only the database sees all three the same way.
    """
    message = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .filter(Message.role == ROLE_AGENT)
        .order_by(Message.id.desc())
        .first()
    )

    if message is None or not message.reasoning_json:
        return None, False, []

    reasoning = Reasoning.from_json(message.reasoning_json)

    if reasoning is None:
        return None, False, []

    return reasoning.rule, bool(reasoning.escalated), list(reasoning.signals or ())


class WebSurface:
    """A browser on the storefront, over real HTTP."""

    name = "web"

    def __init__(self, db: Session, client) -> None:
        self.db = db
        self.client = client
        self.token: str | None = None
        self.conversation_id: int | None = None
        self.opening: list[str] = []

    def open(self) -> None:
        started = self.client.post("/api/v1/sales/conversations")
        started.raise_for_status()
        body = started.json()

        self.token = body["token"]
        self.opening = [message["body"] for message in body.get("messages", [])]

        conversation = (
            self.db.query(Conversation)
            .filter(Conversation.public_token == self.token)
            .one()
        )
        self.conversation_id = conversation.id

    def say(self, text: str) -> Turn:
        response = self.client.post(
            f"/api/v1/sales/conversations/{self.token}/messages",
            json={"body": text},
        )

        if response.status_code >= 400:
            return Turn(
                said=text,
                replies=[f"<HTTP {response.status_code}: {response.text[:200]}>"],
                rule="<http_error>",
                escalated=False,
                stage=None,
                signals=[],
            )

        reply = response.json()
        rule, escalated, signals = _reasoning_of(self.db, self.conversation_id)
        conversation = self.db.get(Conversation, self.conversation_id)

        return Turn(
            said=text,
            replies=[reply["body"]],
            rule=rule,
            escalated=escalated,
            stage=conversation.stage if conversation else None,
            signals=signals,
        )

    def checkout(self, persona) -> str | None:
        """Submit the buy panel, which is how a web buyer reaches a payment page.

        The chat surfaces put a payment link in the thread; the widget does not.
        ``chat.js`` reveals a name/email/company form once the stage reaches
        ``ready_to_buy`` and POSTs it here, then redirects the browser. So a
        simulation that only typed messages would conclude web buyers cannot pay,
        which is wrong — and worse, it would hide whether this endpoint prices the
        build the same way the conversation just did.
        """
        response = self.client.post(
            f"/api/v1/sales/conversations/{self.token}/checkout",
            json={
                "name": persona.name,
                "email": persona.email,
                "company": persona.company,
            },
        )

        if response.status_code >= 400:
            return None

        return response.json().get("checkout_url")


class _MessengerSurface:
    """Shared machinery for the two chat platforms.

    Both arrive as a provider payload, get parsed by the real parser, and are
    answered by ``InboundMessagingService``. Only the payload shape and the
    channel name differ, so only those are subclass responsibilities.
    """

    name = "override me"
    channel = "override me"

    def __init__(self, db: Session, external_id: str) -> None:
        self.db = db
        self.external_id = external_id
        self.service = InboundMessagingService(db)
        self.organization_id = storefront_organization_id(db)
        self.conversation_id: int | None = None
        self.opening: list[str] = []
        self._delivery = 0

    def open(self) -> None:
        """Messengers have no separate open — the first message starts it.

        Left as a no-op rather than sending a synthetic "hi", because an
        injected first turn would hide exactly the greeting-duplication and
        first-contact behaviour this is meant to observe.
        """

    def _message(self, text: str) -> InboundMessage:
        self._delivery += 1

        return InboundMessage(
            channel=self.channel,
            external_id=self.external_id,
            delivery_id=f"{self.name}-{self.external_id}-{self._delivery}",
            kind=KIND_COMMAND if text.startswith("/") else KIND_TEXT,
            text=text,
            command=text.split()[0].lstrip("/") if text.startswith("/") else "",
            sender_name="Simulated Buyer",
        )

    def say(self, text: str) -> Turn:
        handled = self.service.handle(self.organization_id, self._message(text))

        if handled.conversation is not None:
            self.conversation_id = handled.conversation.id

        rule, escalated, signals = (None, False, [])
        stage = None

        if self.conversation_id is not None:
            rule, escalated, signals = _reasoning_of(self.db, self.conversation_id)
            conversation = self.db.get(Conversation, self.conversation_id)
            stage = conversation.stage if conversation else None

        return Turn(
            said=text,
            replies=list(handled.replies),
            rule=rule,
            escalated=escalated,
            stage=stage,
            signals=signals,
        )

    def checkout(self, persona) -> str | None:
        """Nothing to do: the link arrives in the thread on its own.

        ``InboundMessagingService`` calls ``ClosingService.close`` after every
        reply, so a messenger buyer who has given contact details already has a
        link. Kept as a method so the two kinds of surface are interchangeable to
        a caller that just wants a buyer through to a payment page.
        """
        return None


class TelegramSurface(_MessengerSurface):
    name = "telegram"
    channel = CHANNEL_TELEGRAM


class WhatsAppSurface(_MessengerSurface):
    name = "whatsapp"
    channel = CHANNEL_WHATSAPP


SURFACE_NAMES = ("web", "telegram", "whatsapp")


def build_surface(name: str, db: Session, client, external_id: str):
    if name == "web":
        return WebSurface(db, client)
    if name == "telegram":
        return TelegramSurface(db, external_id)
    if name == "whatsapp":
        return WhatsAppSurface(db, external_id)

    raise ValueError(f"unknown surface {name!r}")
