"""Reading what Telegram and WhatsApp deliver, and proving they sent it.

Everything here is pure: bytes and dicts in, a dataclass out. No database, no
network, no settings lookups. That is what lets the awkward cases — a delivery
receipt with no message in it, a sticker, a signature off by one byte, a bot
added to a group chat — be tested as data rather than as a live webhook.

Two platforms, two wire formats, one shape at the end of it. The routes in
``app.api.v1.routes.messaging`` never see a ``wamid`` or an ``update_id``.

**Verification is not optional.** A webhook has to be reachable by the platform,
which means reachable by anyone who learns the URL. Unverified, a stranger could
POST a fabricated message and Nera would answer it as a real buyer — into a real
transcript, against a real approval queue. Both verifiers here fail closed: no
secret configured means nothing is accepted, because a deployment that skipped
the secret is exactly the one an attacker is looking for.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from app.models.channel_identity import CHANNEL_TELEGRAM, CHANNEL_WHATSAPP

# What arrived. Text is the only kind the agent can read; the other two exist so
# the caller can answer helpfully instead of going silent.
KIND_TEXT = "text"
KIND_COMMAND = "command"
KIND_UNSUPPORTED = "unsupported"

# Telegram conventions. A messenger user expects these to work, and without
# handling them "/start" — which Telegram sends on the buyer's behalf the moment
# they open the chat, before they have said anything — would be forwarded to the
# agent as though a buyer had typed it.
COMMAND_START = "start"
COMMAND_HELP = "help"
COMMAND_RESET = "reset"

# "/new" is the same intent as "/reset" and is what people try first.
_COMMAND_ALIASES = {"new": COMMAND_RESET, "restart": COMMAND_RESET}


@dataclass(frozen=True)
class InboundMessage:
    """One message from one person, in the only shape the rest of the code sees."""

    channel: str

    # The platform's handle for the person: a Telegram chat id, a WhatsApp
    # ``wa_id``. This is what ``ChannelIdentity`` is keyed on.
    external_id: str

    # The platform's handle for *this delivery*. Used once, to notice a retry of
    # something already answered.
    delivery_id: str

    kind: str
    text: str = ""
    command: str = ""
    sender_name: str | None = None

    # "photo", "sticker", "voice note" — phrased for a reply, not for a log.
    media_kind: str | None = None


# ---------- verification ----------


def verify_telegram_secret(presented: str | None, expected: str) -> bool:
    """Check the token Telegram echoes in ``X-Telegram-Bot-Api-Secret-Token``.

    Telegram does not sign the body; it repeats a secret chosen at setWebhook
    time. That makes this a shared-secret check, so it is compared in constant
    time and an unset expectation rejects everything.
    """
    if not expected or not presented:
        return False

    return hmac.compare_digest(presented, expected)


def verify_whatsapp_signature(header: str | None, body: bytes, secret: str) -> bool:
    """Check Meta's ``X-Hub-Signature-256`` over the exact bytes delivered.

    The digest covers the raw body, so the caller must hand over the bytes as
    received. Re-serialising the parsed JSON would change key order and
    whitespace and fail every time — correctly, which is why the route reads
    ``await request.body()`` before parsing.
    """
    if not secret or not header:
        return False

    prefix, _, digest = header.partition("=")

    if prefix != "sha256" or not digest:
        return False

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    return hmac.compare_digest(digest.lower(), expected)


# ---------- Telegram ----------


def parse_telegram_update(payload: Any) -> InboundMessage | None:
    """One Telegram update, or None if it is not a message to answer.

    None covers a great deal: edited messages, channel posts, callback queries,
    joins and leaves, and anything from a group. Returning None rather than
    raising is deliberate — an update we have no use for is not an error, and a
    webhook that 500s on one teaches Telegram to retry it forever.
    """
    if not isinstance(payload, dict):
        return None

    message = payload.get("message")

    # Only fresh messages. An edit re-delivered as new text would be answered a
    # second time, which reads as the agent repeating itself for no reason.
    if not isinstance(message, dict):
        return None

    chat = message.get("chat")

    if not isinstance(chat, dict):
        return None

    # Groups and channels are excluded on purpose. A bot added to a group
    # receives every message in it, and a sales agent replying to each one would
    # be indistinguishable from spam.
    if chat.get("type") != "private":
        return None

    chat_id = chat.get("id")

    if chat_id is None:
        return None

    # The update id, not the message id: it is the update that Telegram retries
    # until it is acknowledged, so it is the retry that has to be recognised.
    update_id = payload.get("update_id")
    delivery_id = f"tg:{update_id}" if update_id is not None else None

    if delivery_id is None:
        return None

    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    name = _telegram_name(sender)
    text = message.get("text")

    if not isinstance(text, str) or not text.strip():
        return InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id=str(chat_id),
            delivery_id=delivery_id,
            kind=KIND_UNSUPPORTED,
            sender_name=name,
            media_kind=_telegram_media_kind(message),
        )

    text = text.strip()
    command = _telegram_command(text)

    if command:
        return InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id=str(chat_id),
            delivery_id=delivery_id,
            kind=KIND_COMMAND,
            command=command,
            text=text,
            sender_name=name,
        )

    return InboundMessage(
        channel=CHANNEL_TELEGRAM,
        external_id=str(chat_id),
        delivery_id=delivery_id,
        kind=KIND_TEXT,
        text=text,
        sender_name=name,
    )


def _telegram_command(text: str) -> str:
    """"/start", "/start@NeraBot" and "/Start" are all the start command."""
    if not text.startswith("/"):
        return ""

    word = text[1:].split()[0] if len(text) > 1 else ""
    # Telegram appends "@botname" when more than one bot could be listening.
    word = word.split("@")[0].lower()

    if not word:
        return ""

    return _COMMAND_ALIASES.get(word, word)


def _telegram_name(sender: dict) -> str | None:
    parts = [sender.get("first_name"), sender.get("last_name")]
    name = " ".join(str(p).strip() for p in parts if p)

    return name or (str(sender["username"]) if sender.get("username") else None)


_TELEGRAM_MEDIA = (
    ("photo", "photo"),
    ("voice", "voice note"),
    ("audio", "audio file"),
    ("video", "video"),
    ("video_note", "video note"),
    ("sticker", "sticker"),
    ("document", "file"),
    ("location", "location"),
    ("contact", "contact card"),
)


def _telegram_media_kind(message: dict) -> str | None:
    for key, label in _TELEGRAM_MEDIA:
        if message.get(key):
            return label

    return None


# ---------- WhatsApp ----------


def parse_whatsapp_payload(payload: Any) -> list[InboundMessage]:
    """Every buyer message in one Meta delivery.

    A list, because Meta batches: one POST can carry several messages, from
    several people, across several entries. It can also carry none — most
    deliveries in a busy account are ``statuses`` blocks reporting that an
    outbound message was read, and answering those would mean replying to our
    own delivery receipts.
    """
    if not isinstance(payload, dict):
        return []

    found: list[InboundMessage] = []

    for entry in _items(payload.get("entry")):
        for change in _items(entry.get("changes")):
            value = change.get("value")

            if not isinstance(value, dict):
                continue

            names = _whatsapp_names(value)

            for message in _items(value.get("messages")):
                parsed = _parse_whatsapp_message(message, names)

                if parsed is not None:
                    found.append(parsed)

    return found


def _parse_whatsapp_message(
    message: dict,
    names: dict[str, str],
) -> InboundMessage | None:
    sender = message.get("from")
    message_id = message.get("id")

    if not sender or not message_id:
        return None

    external_id = str(sender)
    delivery_id = f"wa:{message_id}"
    name = names.get(external_id)
    kind = message.get("type")

    if kind == "text":
        body = message.get("text")
        body = body.get("body") if isinstance(body, dict) else None

        if isinstance(body, str) and body.strip():
            return InboundMessage(
                channel=CHANNEL_WHATSAPP,
                external_id=external_id,
                delivery_id=delivery_id,
                kind=KIND_TEXT,
                text=body.strip(),
                sender_name=name,
            )

    # A tapped quick-reply button carries its label where the text would be.
    # Treating it as typed text is right: the buyer chose those words.
    if kind == "button":
        body = message.get("button")
        body = body.get("text") if isinstance(body, dict) else None

        if isinstance(body, str) and body.strip():
            return InboundMessage(
                channel=CHANNEL_WHATSAPP,
                external_id=external_id,
                delivery_id=delivery_id,
                kind=KIND_TEXT,
                text=body.strip(),
                sender_name=name,
            )

    return InboundMessage(
        channel=CHANNEL_WHATSAPP,
        external_id=external_id,
        delivery_id=delivery_id,
        kind=KIND_UNSUPPORTED,
        sender_name=name,
        media_kind=_WHATSAPP_MEDIA.get(str(kind), None),
    )


_WHATSAPP_MEDIA = {
    "image": "photo",
    "audio": "audio message",
    "voice": "voice note",
    "video": "video",
    "sticker": "sticker",
    "document": "file",
    "location": "location",
    "contacts": "contact card",
}


def _whatsapp_names(value: dict) -> dict[str, str]:
    """``wa_id`` to profile name, from the contacts block beside the messages."""
    names: dict[str, str] = {}

    for contact in _items(value.get("contacts")):
        wa_id = contact.get("wa_id")
        profile = contact.get("profile")
        name = profile.get("name") if isinstance(profile, dict) else None

        if wa_id and isinstance(name, str) and name.strip():
            names[str(wa_id)] = name.strip()

    return names


def _items(value: Any) -> list[dict]:
    """Only the dicts in what should have been a list of them.

    Webhook payloads are outside our control, and a single unexpected null in a
    batch of twenty must not cost the other nineteen their replies.
    """
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]
