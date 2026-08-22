"""Reading what Telegram and WhatsApp actually deliver.

These are the payloads that arrive when nothing interesting has happened, which
is most of them. A webhook that treats every delivery as a buyer's question would
answer delivery receipts, reply to itself in group chats, and re-answer edited
messages.

The signature tests matter more than they look. A webhook has to be reachable by
the platform, therefore by anyone who learns the URL. If verification passes when
no secret is configured, then the deployment that forgot to set one accepts
fabricated buyer messages from strangers — into a real transcript, against a real
approval queue. Both verifiers must fail closed.
"""

import hashlib
import hmac
import json

import pytest

from app.messaging.inbound import (
    COMMAND_HELP,
    COMMAND_RESET,
    COMMAND_START,
    KIND_COMMAND,
    KIND_TEXT,
    KIND_UNSUPPORTED,
    parse_telegram_update,
    parse_whatsapp_payload,
    verify_telegram_secret,
    verify_whatsapp_signature,
)
from app.models.channel_identity import CHANNEL_TELEGRAM, CHANNEL_WHATSAPP

SECRET = "a-shared-secret-value"


def telegram_update(update_id=1, text="What does it cost?", chat_type="private", **extra):
    message = {
        "message_id": 10,
        "from": {"id": 99, "first_name": "Ada", "last_name": "Nwosu"},
        "chat": {"id": 4242, "type": chat_type},
        "date": 1787387557,
    }

    if text is not None:
        message["text"] = text

    message.update(extra)

    return {"update_id": update_id, "message": message}


def whatsapp_payload(messages, contacts=None):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550001111",
                                "phone_number_id": "PHONE_ID",
                            },
                            "contacts": contacts or [],
                            "messages": messages,
                        },
                    }
                ],
            }
        ],
    }


def wa_text(body="How much is it?", sender="2348012345678", message_id="wamid.ABC"):
    return {
        "from": sender,
        "id": message_id,
        "timestamp": "1787387557",
        "type": "text",
        "text": {"body": body},
    }


# ---------- Telegram: verifying ----------


def test_the_matching_secret_token_is_accepted():
    assert verify_telegram_secret(SECRET, SECRET) is True


def test_a_wrong_secret_token_is_refused():
    assert verify_telegram_secret("not-it", SECRET) is False


def test_no_secret_token_presented_is_refused():
    assert verify_telegram_secret(None, SECRET) is False


def test_an_unconfigured_secret_refuses_everything():
    """The deployment that forgot to set one is the one worth attacking.

    Failing open here would mean a stranger who learns the URL can put words in
    a buyer's mouth, and the operator would have no way to notice.
    """
    assert verify_telegram_secret("anything at all", "") is False
    assert verify_telegram_secret("", "") is False


# ---------- Telegram: parsing ----------


def test_a_private_text_message_is_read():
    message = parse_telegram_update(telegram_update())

    assert message is not None
    assert message.channel == CHANNEL_TELEGRAM
    assert message.external_id == "4242"
    assert message.kind == KIND_TEXT
    assert message.text == "What does it cost?"
    assert message.sender_name == "Ada Nwosu"


def test_the_delivery_id_is_the_update_id():
    """Telegram retries the *update*, so that is what identifies a redelivery."""
    assert parse_telegram_update(telegram_update(update_id=771)).delivery_id == "tg:771"


def test_a_group_message_is_ignored():
    """A bot in a group receives every message in it; answering each would be spam."""
    assert parse_telegram_update(telegram_update(chat_type="group")) is None
    assert parse_telegram_update(telegram_update(chat_type="supergroup")) is None


def test_an_edited_message_is_ignored():
    """Re-answering an edit reads as the agent repeating itself unprompted."""
    edited = {"update_id": 5, "edited_message": telegram_update()["message"]}

    assert parse_telegram_update(edited) is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"update_id": 1},
        {"update_id": 1, "callback_query": {"id": "x"}},
        {"update_id": 1, "message": {"chat": {"type": "private"}}},  # no chat id
        {"message": telegram_update()["message"]},  # no update_id
        "not a dict",
        None,
    ],
)
def test_an_update_with_nothing_to_answer_is_ignored(payload):
    """None rather than an exception: a 500 teaches Telegram to retry forever."""
    assert parse_telegram_update(payload) is None


def test_a_sticker_is_read_as_something_unsupported():
    message = parse_telegram_update(telegram_update(text=None, sticker={"file_id": "s"}))

    assert message.kind == KIND_UNSUPPORTED
    assert message.media_kind == "sticker"


def test_a_voice_note_names_itself_for_the_reply():
    """The label is phrased for a buyer to read, not for a log."""
    message = parse_telegram_update(telegram_update(text=None, voice={"file_id": "v"}))

    assert message.media_kind == "voice note"


def test_an_empty_text_message_is_not_treated_as_a_question():
    assert parse_telegram_update(telegram_update(text="   ")).kind == KIND_UNSUPPORTED


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/start", COMMAND_START),
        ("/Start", COMMAND_START),
        ("/start@nekoflowaibot", COMMAND_START),
        ("/start hello", COMMAND_START),
        ("/reset", COMMAND_RESET),
        ("/new", COMMAND_RESET),
        ("/restart", COMMAND_RESET),
        ("/help", COMMAND_HELP),
    ],
)
def test_the_commands_a_telegram_user_expects(text, expected):
    message = parse_telegram_update(telegram_update(text=text))

    assert message.kind == KIND_COMMAND
    assert message.command == expected


def test_a_slash_is_not_enough_to_be_a_command():
    assert parse_telegram_update(telegram_update(text="/")).kind == KIND_TEXT


def test_a_price_with_a_slash_in_it_is_still_text():
    message = parse_telegram_update(telegram_update(text="is it 50/50 split?"))

    assert message.kind == KIND_TEXT


def test_a_username_stands_in_for_a_missing_name():
    update = telegram_update()
    update["message"]["from"] = {"id": 9, "username": "adan"}

    assert parse_telegram_update(update).sender_name == "adan"


# ---------- WhatsApp: verifying ----------


def signature_for(body: bytes, secret: str = SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    return f"sha256={digest}"


def test_a_correct_signature_over_the_raw_body_is_accepted():
    body = json.dumps(whatsapp_payload([wa_text()])).encode()

    assert verify_whatsapp_signature(signature_for(body), body, SECRET) is True


def test_a_signature_over_different_bytes_is_refused():
    """Why the route must read request.body() before parsing.

    Re-serialising parsed JSON changes key order and whitespace, so the digest
    would never match — correctly. This is that failure, made explicit.
    """
    original = json.dumps(whatsapp_payload([wa_text()])).encode()
    reserialised = json.dumps(json.loads(original), indent=2).encode()

    assert verify_whatsapp_signature(signature_for(original), reserialised, SECRET) is False


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "sha256=",
        "deadbeef",                      # no algorithm prefix
        "sha1=deadbeef",                 # the algorithm Meta stopped using
        "sha256=not-hex-at-all",
    ],
)
def test_a_malformed_signature_header_is_refused(header):
    assert verify_whatsapp_signature(header, b"{}", SECRET) is False


def test_an_unconfigured_app_secret_refuses_everything():
    body = b"{}"

    assert verify_whatsapp_signature(signature_for(body, ""), body, "") is False


def test_the_signature_is_case_insensitive_in_hex():
    """Meta sends lowercase, but hex is hex and a mismatch here would be absurd."""
    body = json.dumps(whatsapp_payload([wa_text()])).encode()
    upper = signature_for(body).upper().replace("SHA256", "sha256")

    assert verify_whatsapp_signature(upper, body, SECRET) is True


# ---------- WhatsApp: parsing ----------


def test_a_text_message_is_read():
    found = parse_whatsapp_payload(whatsapp_payload([wa_text()]))

    assert len(found) == 1
    assert found[0].channel == CHANNEL_WHATSAPP
    assert found[0].external_id == "2348012345678"
    assert found[0].delivery_id == "wa:wamid.ABC"
    assert found[0].kind == KIND_TEXT
    assert found[0].text == "How much is it?"


def test_a_batch_carries_every_message_in_it():
    """Meta batches, so one POST can be several buyers at once."""
    found = parse_whatsapp_payload(
        whatsapp_payload(
            [
                wa_text("first", sender="111", message_id="wamid.A"),
                wa_text("second", sender="222", message_id="wamid.B"),
            ]
        )
    )

    assert [m.text for m in found] == ["first", "second"]
    assert [m.external_id for m in found] == ["111", "222"]


def test_a_status_only_delivery_carries_no_messages():
    """Most deliveries on a busy account are read receipts for our own sends."""
    payload = whatsapp_payload([])
    payload["entry"][0]["changes"][0]["value"]["statuses"] = [
        {"id": "wamid.OUT", "status": "read", "recipient_id": "2348012345678"}
    ]

    assert parse_whatsapp_payload(payload) == []


def test_the_profile_name_beside_the_message_is_picked_up():
    found = parse_whatsapp_payload(
        whatsapp_payload(
            [wa_text()],
            contacts=[
                {"wa_id": "2348012345678", "profile": {"name": "Ada Nwosu"}}
            ],
        )
    )

    assert found[0].sender_name == "Ada Nwosu"


def test_a_tapped_quick_reply_button_counts_as_typed_text():
    """The buyer chose those words, so they are the buyer's words."""
    button = {
        "from": "2348012345678",
        "id": "wamid.BTN",
        "type": "button",
        "button": {"text": "Tell me the price", "payload": "PRICE"},
    }

    found = parse_whatsapp_payload(whatsapp_payload([button]))

    assert found[0].kind == KIND_TEXT
    assert found[0].text == "Tell me the price"


def test_an_image_is_read_as_something_unsupported():
    image = {
        "from": "2348012345678",
        "id": "wamid.IMG",
        "type": "image",
        "image": {"id": "media-1", "mime_type": "image/jpeg"},
    }

    found = parse_whatsapp_payload(whatsapp_payload([image]))

    assert found[0].kind == KIND_UNSUPPORTED
    assert found[0].media_kind == "photo"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        None,
        "not a dict",
        {"entry": None},
        {"entry": [None, "nonsense"]},
        {"entry": [{"changes": None}]},
        {"entry": [{"changes": [{"value": None}]}]},
        {"entry": [{"changes": [{"value": {"messages": "not a list"}}]}]},
    ],
)
def test_a_payload_with_nothing_in_it_yields_nothing(payload):
    assert parse_whatsapp_payload(payload) == []


def test_one_malformed_message_does_not_cost_the_others_their_replies():
    found = parse_whatsapp_payload(
        whatsapp_payload(
            [
                {"type": "text", "text": {"body": "no sender or id"}},
                wa_text("a real question", message_id="wamid.OK"),
            ]
        )
    )

    assert [m.text for m in found] == ["a real question"]
