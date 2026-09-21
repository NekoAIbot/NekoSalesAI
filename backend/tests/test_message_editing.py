"""Tests for Telegram in-place message editing on multi-select steps."""

import pytest

from app.config.settings import settings
from app.messaging.clients import TelegramClient
from app.messaging.inbound import InboundMessage, KIND_TEXT, parse_telegram_update
from app.messaging.service import InboundMessagingService
from app.models.channel_identity import CHANNEL_TELEGRAM
from app.models.organization import Organization


@pytest.fixture
def storefront(db):
    org = Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


class RecordingTransport:
    """A fake transport that records every call and can simulate edit results."""

    def __init__(self, edit_ok=True):
        self.calls = []
        self.edit_ok = edit_ok

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs.get("json", {})))
        if "editMessageText" in url:
            ok = self.edit_ok
            return _FakeResponse(200, {"ok": ok, "result": ok})
        return _FakeResponse(200, {"ok": True, "result": {"message_id": 1}})


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body

    @property
    def text(self):
        return str(self._body)


def test_callback_query_carries_its_message_id():
    """The parsed callback knows which message the button was attached to."""
    msg = parse_telegram_update(
        {
            "update_id": 7,
            "callback_query": {
                "id": "55",
                "from": {"id": 42, "first_name": "Ada"},
                "message": {
                    "message_id": 901,
                    "chat": {"id": 42, "type": "private"},
                },
                "data": "scoping:channels:web",
            },
        }
    )
    assert msg is not None
    assert msg.callback_message_id == 901
    assert msg.text == "scoping:channels:web"


def test_a_plain_message_has_no_callback_message_id():
    msg = parse_telegram_update(
        {
            "update_id": 8,
            "message": {
                "message_id": 902,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "first_name": "Ada"},
                "text": "hello",
            },
        }
    )
    assert msg is not None
    assert msg.callback_message_id is None


def test_edit_message_text_posts_the_right_payload():
    transport = RecordingTransport()
    client = TelegramClient(bot_token="t", transport=transport)

    ok = client.edit_message_text(
        "42",
        901,
        "Which channels? ✓ WhatsApp",
        [[{"text": "✓ WhatsApp", "callback_data": "scoping:channels:whatsapp"}]],
    )

    assert ok is True
    url, payload = transport.calls[0]
    assert "editMessageText" in url
    assert payload["chat_id"] == "42"
    assert payload["message_id"] == 901
    assert payload["reply_markup"]["inline_keyboard"][0][0]["text"].startswith("✓")


def test_edit_failure_is_reported_not_raised():
    transport = RecordingTransport(edit_ok=False)
    client = TelegramClient(bot_token="t", transport=transport)

    ok = client.edit_message_text("42", 901, "text")

    assert ok is False  # caller falls back to a fresh send


def test_a_callback_rerender_edits_instead_of_sending(db, storefront):
    """The multi-select re-render edits the source message, not a new one."""
    transport = RecordingTransport()
    telegram = TelegramClient(bot_token="t", transport=transport)
    service = InboundMessagingService(db, telegram=telegram)

    # First message opens the thread and lands on the products step.
    service.handle(
        storefront.id,
        InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="42",
            delivery_id="tg:1",
            kind=KIND_TEXT,
            text="I need an AI",
        ),
    )

    # A callback tap on the channels step (products answered by text first).
    service.handle(
        storefront.id,
        InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="42",
            delivery_id="tg:2",
            kind=KIND_TEXT,
            text="sales agent",
        ),
    )

    before = len(transport.calls)
    service.handle(
        storefront.id,
        InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="42",
            delivery_id="tgcb:3",
            kind=KIND_TEXT,
            text="scoping:channels:web",
            callback_message_id=901,
        ),
    )

    # The re-render the flow produced carries an inline keyboard.
    from app.messaging.presentation import ChannelMessage

    rerender = ChannelMessage(
        text="Which channels? ✓ Website",
        telegram_inline_keyboard=(
            ({"text": "✓ Website", "callback_data": "scoping:channels:web"},),
            ({"text": "➡️ Next", "callback_data": "scoping:channels:__next__"},),
        ),
    )
    service.deliver(
        InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="42",
            delivery_id="tgcb:3",
            kind=KIND_TEXT,
            text="scoping:channels:web",
            callback_message_id=901,
        ),
        [rerender.text],
        [rerender],
    )

    # The re-render went out as an edit, not a fresh sendMessage.
    edits = [c for c in transport.calls[before:] if "editMessageText" in c[0]]
    assert edits, "the callback re-render should edit the source message"
    assert edits[0][1]["message_id"] == 901


def test_a_plain_text_reply_still_sends_normally(db, storefront):
    """Only callback re-renders edit; ordinary replies still send."""
    transport = RecordingTransport()
    telegram = TelegramClient(bot_token="t", transport=transport)
    service = InboundMessagingService(db, telegram=telegram)

    service.handle(
        storefront.id,
        InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="42",
            delivery_id="tg:1",
            kind=KIND_TEXT,
            text="hello",
        ),
    )
    service.deliver(
        InboundMessage(
            channel=CHANNEL_TELEGRAM,
            external_id="42",
            delivery_id="tg:1",
            kind=KIND_TEXT,
            text="hello",
        ),
        ["A plain reply."],
    )

    assert any("sendMessage" in c[0] for c in transport.calls)
    assert not any("editMessageText" in c[0] for c in transport.calls)
