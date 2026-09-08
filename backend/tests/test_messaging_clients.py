"""Sending, and the platform limits that make a long message vanish.

Telegram refuses a ``sendMessage`` over 4,096 characters and WhatsApp refuses the
same figure for a text body. Both refusals are logged and swallowed by
``DeliveryPusher``, on purpose — a chat platform being down must not cost a buyer
the thing they bought. The consequence is that "the message got too long" and "the
platform is down" look identical from the outside, so an over-long send is a
silent failure: every counter says delivered, and the buyer sees nothing.

Install guidance is thousands of characters, which turned that from a theoretical
risk into a live one. Delivery composes itself as several right-sized parts, and
this splitter is the net under that — for the follow-up copy nobody re-measured
after editing, and for the company name that pushed a borderline message over.
"""

from app.messaging.clients import (
    MESSAGE_LIMIT,
    TelegramClient,
    WhatsAppClient,
    split_for_delivery,
)


class Recorder:
    """A transport that records every send and reports success."""

    def __init__(self) -> None:
        self.posts: list[dict] = []

    def post(self, url: str, **kwargs):
        self.posts.append({"url": url, **kwargs})

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"ok": True, "result": {"message_id": 1}}

        return Response()


# ---------- the splitter ----------


def test_a_short_message_is_left_exactly_as_it_is():
    assert split_for_delivery("hello") == ["hello"]


def test_every_piece_fits_under_the_limit():
    text = "\n\n".join(f"paragraph {index} " + "x" * 200 for index in range(100))

    pieces = split_for_delivery(text)

    assert len(pieces) > 1
    assert all(len(piece) <= MESSAGE_LIMIT for piece in pieces)


def test_nothing_is_lost_in_the_split():
    """A splitter that drops content is worse than one that fails loudly."""
    text = "\n\n".join(f"paragraph {index}" for index in range(2000))

    rejoined = "".join(split_for_delivery(text))

    for index in (0, 999, 1999):
        assert f"paragraph {index}" in rejoined


def test_it_breaks_between_paragraphs_rather_than_through_them():
    """Install steps cut through the middle are worse than no install steps."""
    block = "step one\nstep two\nstep three"
    text = "\n\n".join([block] * 400)

    pieces = split_for_delivery(text)

    # Every piece starts and ends on a whole line of the original.
    for piece in pieces:
        assert piece.startswith("step ")
        assert piece.rstrip().endswith(("one", "two", "three"))


def test_the_widget_snippet_survives_intact():
    """The one piece of text where a mid-line break makes it useless."""
    snippet = (
        '<script src="https://example.com/static/js/widget.js"\n'
        '        data-token="tok-abc" async></script>'
    )
    text = ("filler paragraph\n\n" * 300) + snippet

    pieces = split_for_delivery(text)

    assert any(snippet in piece for piece in pieces)


def test_one_enormous_unbroken_line_is_cut_rather_than_dropped():
    """No boundary to respect, so there is nothing to preserve — but it still goes."""
    text = "z" * (MESSAGE_LIMIT * 3)

    pieces = split_for_delivery(text)

    assert all(len(piece) <= MESSAGE_LIMIT for piece in pieces)
    assert sum(len(piece) for piece in pieces) == len(text)


# ---------- the clients using it ----------


def test_telegram_sends_a_long_message_as_several():
    recorder = Recorder()
    client = TelegramClient(bot_token="t", transport=recorder)

    client.send_message("42", "\n\n".join("y" * 500 for _ in range(30)))

    assert len(recorder.posts) > 1
    assert all(
        len(post["json"]["text"]) <= MESSAGE_LIMIT for post in recorder.posts
    )
    assert all(post["json"]["chat_id"] == "42" for post in recorder.posts)


def test_telegram_still_sends_a_normal_message_as_one():
    recorder = Recorder()
    client = TelegramClient(bot_token="t", transport=recorder)

    client.send_message("42", "your workspace is live")

    assert len(recorder.posts) == 1
    assert recorder.posts[0]["json"]["text"] == "your workspace is live"


def test_whatsapp_sends_a_long_message_as_several():
    recorder = Recorder()
    client = WhatsAppClient(
        access_token="t",
        phone_number_id="1",
        transport=recorder,
    )

    client.send_message("+2348000000000", "\n\n".join("y" * 500 for _ in range(30)))

    assert len(recorder.posts) > 1
    assert all(
        len(post["json"]["text"]["body"]) <= MESSAGE_LIMIT
        for post in recorder.posts
    )
