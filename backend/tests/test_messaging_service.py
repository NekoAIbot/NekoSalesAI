"""A buyer talking to Nera on a messenger, and staying the same buyer.

The property everything here defends: a messenger carries no session. Each
delivery arrives with a chat id and nothing else, so without ``ChannelIdentity``
every message opens a fresh conversation — the agent greets the same person
forever and the stage machine never advances past the first turn. That failure is
invisible in a single-message test, which is why most of these send two.

The other property is that a messenger is a *pipe*, not a second agent. A buyer
who asks for a discount on Telegram must get the same refusal, the same
escalation and the same approval row as one who asks in the browser — otherwise
the platform with the weakest guard becomes the one people use to extract a
promise the business has to honour.
"""

import pytest

from app.messaging.inbound import (
    COMMAND_HELP,
    COMMAND_RESET,
    COMMAND_START,
    KIND_COMMAND,
    KIND_TEXT,
    KIND_UNSUPPORTED,
    InboundMessage,
)
from app.messaging.service import InboundMessagingService, storefront_organization_id
from app.models.approval_request import ApprovalRequest
from app.models.channel_identity import (
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    ChannelIdentity,
)
from app.models.conversation import ROLE_VISITOR, Conversation, Message
from app.models.lead import Lead
from app.models.organization import Organization
from app.sales.service import MAX_MESSAGE_LENGTH


@pytest.fixture
def storefront(db):
    """The organization the deployment's own bot answers for."""
    from app.config.settings import settings

    org = Organization(name="NekoSalesAI", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)

    return org


class FakeClient:
    def __init__(self):
        self.sent = []

    def send_message(self, destination, text):
        self.sent.append((destination, text))


@pytest.fixture
def telegram():
    return FakeClient()


@pytest.fixture
def whatsapp():
    return FakeClient()


@pytest.fixture
def service(db, telegram, whatsapp):
    return InboundMessagingService(db, telegram=telegram, whatsapp=whatsapp)


_counter = {"n": 0}


def inbound(
    text="What does it cost?",
    *,
    kind=KIND_TEXT,
    channel=CHANNEL_TELEGRAM,
    external_id="4242",
    delivery_id=None,
    command="",
    sender_name="Ada Nwosu",
    media_kind=None,
):
    """One message, with a distinct delivery id unless one is pinned.

    Distinct by default because a repeated id is exactly what the dedupe guard
    suppresses — sharing one accidentally would make a test pass by not
    happening.
    """
    if delivery_id is None:
        _counter["n"] += 1
        delivery_id = f"tg:{_counter['n']}"

    return InboundMessage(
        channel=channel,
        external_id=external_id,
        delivery_id=delivery_id,
        kind=kind,
        text=text,
        command=command,
        sender_name=sender_name,
        media_kind=media_kind,
    )


# ---------- routing ----------


def test_the_storefront_is_who_the_deployments_bot_answers_for(db, storefront):
    assert storefront_organization_id(db) == storefront.id


def test_an_unseeded_database_has_nobody_to_answer_for(db):
    """The callers drop the message rather than opening a thread against nothing."""
    assert storefront_organization_id(db) is None


# ---------- first contact ----------


def test_first_contact_greets_and_then_answers(service, storefront):
    handled = service.handle(storefront.id, inbound("What does it cost?"))

    # Two messages: Nera introduces itself, then answers what was asked. One
    # would mean the buyer either never learns who they are talking to or never
    # gets their question answered.
    assert len(handled.replies) == 2
    assert handled.replies[0]
    assert handled.replies[1]


def test_the_greeting_sent_is_the_greeting_in_the_transcript(service, storefront, db):
    """A human reviewing the thread must see what the buyer actually received."""
    handled = service.handle(storefront.id, inbound())

    stored = db.query(Message).order_by(Message.id).all()

    assert stored[0].body == handled.replies[0]


def test_opening_with_hello_is_not_greeted_twice(service, storefront):
    """Found in a real Telegram thread, not reasoned about.

    Nera's answer to "Hi" *is* its greeting, and first contact prepends the
    greeting — so the buyer received the same paragraph twice, back to back, as
    the first thing that ever happened. It reads as a broken bot.
    """
    handled = service.handle(storefront.id, inbound("Hi"))

    assert len(handled.replies) == len(set(handled.replies))


def test_a_real_question_still_gets_both_the_greeting_and_an_answer(service, storefront):
    """The dedupe must not collapse two genuinely different messages into one."""
    handled = service.handle(storefront.id, inbound("What does it cost?"))

    assert len(handled.replies) == 2
    assert handled.replies[0] != handled.replies[1]


def test_first_contact_records_who_is_talking(service, storefront, db):
    service.handle(storefront.id, inbound())

    identity = db.query(ChannelIdentity).one()

    assert identity.channel == CHANNEL_TELEGRAM
    assert identity.external_id == "4242"
    assert identity.organization_id == storefront.id
    assert identity.display_name == "Ada Nwosu"
    assert identity.last_seen_at is not None


def test_the_conversation_belongs_to_the_organization_being_sold(
    service, storefront, db
):
    """The agent answers from *this* org's catalog, as the widget does."""
    service.handle(storefront.id, inbound())

    assert db.query(Conversation).one().organization_id == storefront.id


# ---------- the thing a messenger has no session for ----------


def test_a_second_message_continues_the_same_conversation(service, storefront, db):
    service.handle(storefront.id, inbound("What does it cost?"))
    service.handle(storefront.id, inbound("And what does it include?"))

    assert db.query(Conversation).count() == 1
    assert db.query(ChannelIdentity).count() == 1


def test_the_second_message_is_not_greeted_again(service, storefront):
    service.handle(storefront.id, inbound("What does it cost?"))
    handled = service.handle(storefront.id, inbound("And what does it include?"))

    # One reply, not two. A greeting on every turn is the signature of an agent
    # with no memory, and it is what a chat id with no mapping row produces.
    assert len(handled.replies) == 1


def test_the_whole_exchange_is_in_one_transcript(service, storefront, db):
    service.handle(storefront.id, inbound("What does it cost?"))
    service.handle(storefront.id, inbound("And what does it include?"))

    bodies = [m.body for m in db.query(Message).order_by(Message.id).all()]

    assert "What does it cost?" in bodies
    assert "And what does it include?" in bodies


def test_two_people_on_the_same_channel_get_their_own_threads(service, storefront, db):
    service.handle(storefront.id, inbound("hello", external_id="111"))
    service.handle(storefront.id, inbound("hello", external_id="222"))

    assert db.query(Conversation).count() == 2
    assert db.query(ChannelIdentity).count() == 2


def test_the_same_number_on_two_channels_is_two_identities(service, storefront, db):
    """Telegram chat ids and WhatsApp numbers share a namespace by coincidence."""
    service.handle(storefront.id, inbound("hi", channel=CHANNEL_TELEGRAM, external_id="777"))
    service.handle(storefront.id, inbound("hi", channel=CHANNEL_WHATSAPP, external_id="777"))

    assert db.query(ChannelIdentity).count() == 2


# ---------- retries ----------


def test_the_same_delivery_twice_is_answered_once(service, storefront, db):
    first = service.handle(storefront.id, inbound(delivery_id="tg:500"))
    again = service.handle(storefront.id, inbound(delivery_id="tg:500"))

    assert again.duplicate is True
    assert again.replies == []
    assert first.replies

    # And the transcript did not grow a second copy of the question.
    visitor_turns = (
        db.query(Message)
        .filter(Message.role == ROLE_VISITOR, Message.body == "What does it cost?")
        .count()
    )
    assert visitor_turns == 1


def test_a_redelivery_after_a_reset_is_still_recognised(service, storefront):
    """The marker follows the identity to whichever thread it now points at."""
    service.handle(storefront.id, inbound())
    service.handle(storefront.id, inbound(kind=KIND_COMMAND, command=COMMAND_RESET,
                                          text="/reset", delivery_id="tg:900"))
    again = service.handle(
        storefront.id,
        inbound(kind=KIND_COMMAND, command=COMMAND_RESET, text="/reset",
                delivery_id="tg:900"),
    )

    assert again.duplicate is True


def test_two_different_deliveries_are_both_answered(service, storefront):
    first = service.handle(storefront.id, inbound("one", delivery_id="tg:1001"))
    second = service.handle(storefront.id, inbound("two", delivery_id="tg:1002"))

    assert first.replies
    assert second.replies
    assert second.duplicate is False


# ---------- commands ----------


def test_start_greets_without_opening_a_second_thread(service, storefront, db):
    service.handle(storefront.id, inbound("hello"))
    handled = service.handle(
        storefront.id,
        inbound(kind=KIND_COMMAND, command=COMMAND_START, text="/start"),
    )

    assert handled.replies[0]
    assert db.query(Conversation).count() == 1


def test_start_as_the_very_first_thing_still_greets(service, storefront):
    """Telegram sends /start before the buyer has typed anything at all."""
    handled = service.handle(
        storefront.id,
        inbound(kind=KIND_COMMAND, command=COMMAND_START, text="/start"),
    )

    assert handled.replies
    assert handled.replies[0]


def test_reset_starts_a_fresh_thread_and_repoints_the_identity(service, storefront, db):
    service.handle(storefront.id, inbound("hello"))
    first = db.query(ChannelIdentity).one().conversation_id

    service.handle(
        storefront.id,
        inbound(kind=KIND_COMMAND, command=COMMAND_RESET, text="/reset"),
    )

    assert db.query(Conversation).count() == 2
    assert db.query(ChannelIdentity).one().conversation_id != first


def test_the_old_thread_survives_a_reset(service, storefront, db):
    """It is a sales record. Starting over must not erase what was said."""
    service.handle(storefront.id, inbound("What does it cost?"))
    service.handle(
        storefront.id,
        inbound(kind=KIND_COMMAND, command=COMMAND_RESET, text="/reset"),
    )

    bodies = [m.body for m in db.query(Message).all()]

    assert "What does it cost?" in bodies


def test_help_says_what_nera_cannot_do(service, storefront):
    handled = service.handle(
        storefront.id,
        inbound(kind=KIND_COMMAND, command=COMMAND_HELP, text="/help"),
    )

    text = handled.replies[-1]

    assert "Nera" in text
    assert "/reset" in text
    # The limit is the product's whole claim; help that omitted it would be
    # advertising an agent we do not ship.
    assert "person" in text.lower() or "human" in text.lower()


def test_an_unknown_command_is_read_as_the_question_it_is(service, storefront, db):
    """"/pricing" is a buyer asking about pricing with punctuation in front."""
    service.handle(storefront.id, inbound("hello"))
    service.handle(
        storefront.id,
        inbound(kind=KIND_COMMAND, command="pricing", text="/pricing"),
    )

    bodies = [m.body for m in db.query(Message).all()]

    assert "pricing" in bodies


def test_a_bare_slash_command_falls_back_to_help(service, storefront):
    handled = service.handle(
        storefront.id,
        inbound(kind=KIND_COMMAND, command="", text="/"),
    )

    assert "/reset" in handled.replies[-1]


# ---------- what the agent cannot read ----------


def test_a_photo_gets_an_answer_rather_than_silence(service, storefront):
    handled = service.handle(
        storefront.id,
        inbound(text="", kind=KIND_UNSUPPORTED, media_kind="photo"),
    )

    assert "photo" in handled.replies[-1]


def test_an_unnamed_attachment_still_gets_an_answer(service, storefront):
    handled = service.handle(
        storefront.id,
        inbound(text="", kind=KIND_UNSUPPORTED, media_kind=None),
    )

    assert handled.replies[-1]


def test_an_over_long_message_is_told_why(service, storefront):
    handled = service.handle(storefront.id, inbound("x" * (MAX_MESSAGE_LENGTH + 1)))

    # The limit belongs to the agent, so the explanation does too. Silence would
    # look like the bot being broken.
    assert "too long" in handled.replies[-1].lower()


# ---------- a messenger is a pipe, not a second agent ----------


def test_a_discount_request_is_refused_and_escalated(service, storefront, db):
    """The guard that makes this product worth buying, reached over Telegram."""
    service.handle(storefront.id, inbound("Can you do 40% off if we sign today?"))

    assert db.query(ApprovalRequest).count() == 1


def test_an_email_given_on_a_messenger_becomes_a_lead(service, storefront, db):
    service.handle(storefront.id, inbound("hello"))
    service.handle(storefront.id, inbound("my email is ada@clinic.example"))

    assert db.query(Lead).count() == 1


def test_the_platform_name_is_carried_onto_the_thread(service, storefront, db):
    service.handle(storefront.id, inbound())

    assert db.query(Conversation).one().visitor_name == "Ada Nwosu"


def test_a_handed_off_thread_gets_no_reply_from_the_agent(service, storefront, db):
    from app.sales.service import ConversationService

    service.handle(storefront.id, inbound("hello"))
    conversation = db.query(Conversation).one()
    ConversationService(db).hand_off(conversation, "A human is negotiating.")

    handled = service.handle(storefront.id, inbound("still there?"))

    # Nothing sent. Replying over a colleague mid-negotiation is how an AI
    # contradicts the deal the human just agreed.
    assert handled.replies == []


# ---------- delivering ----------


def test_the_reply_goes_back_on_the_channel_it_came_from(service, storefront, telegram, whatsapp):
    message = inbound()
    handled = service.handle(storefront.id, message)
    service.deliver(message, handled.replies)

    assert len(telegram.sent) == 2
    assert telegram.sent[0][0] == "4242"
    assert whatsapp.sent == []


def test_whatsapp_replies_go_to_whatsapp(service, storefront, telegram, whatsapp):
    message = inbound(channel=CHANNEL_WHATSAPP, external_id="2348012345678")
    handled = service.handle(storefront.id, message)
    service.deliver(message, handled.replies)

    assert len(whatsapp.sent) == 2
    assert telegram.sent == []


def test_an_empty_reply_is_not_sent(service, storefront, telegram):
    service.deliver(inbound(), ["", "   "])

    assert telegram.sent == []


def test_a_failing_send_does_not_stop_the_next_one(db, storefront):
    """A buyer who gets half an answer is better served than one who gets none."""

    class Flaky(FakeClient):
        def send_message(self, destination, text):
            if not self.sent:
                self.sent.append((destination, text))
                raise RuntimeError("rate limited")
            self.sent.append((destination, text))

    flaky = Flaky()
    service = InboundMessagingService(db, telegram=flaky, whatsapp=FakeClient())

    message = inbound()
    handled = service.handle(storefront.id, message)
    service.deliver(message, handled.replies)

    assert len(flaky.sent) == 2


# ---------- one engine, priced the same on every channel ----------
#
# The storefront publishes no tiers. Every figure it quotes is computed from
# four answers, and that intake lives in the agent — which means a messenger
# inherits it or the messenger has no prices at all. These walk the whole thing
# over Telegram rather than trusting that inheritance.
#
# The answers are imported from the web test on purpose. If the same four
# answers ever reach a different number in a browser than on Telegram, that is
# two engines wearing one name, and this is where it shows up.


def walk_the_intake(service, storefront, answers):
    """Send each answer as its own delivery, as a real buyer's phone would."""
    replies = []

    for answer in answers:
        replies.extend(service.handle(storefront.id, inbound(answer)).replies)

    return replies


def test_a_telegram_buyer_reaches_a_computed_price(service, storefront, db):
    """The whole intake, over the pipe, ending at a real figure."""
    from tests.test_checkout import INTAKE_ANSWERS, SALES_QUOTE

    replies = walk_the_intake(service, storefront, INTAKE_ANSWERS)

    conversation = db.query(Conversation).one()
    assert conversation.stage == "ready_to_buy"

    # The figure the engine derives for this build, in the message that was
    # actually sent to the phone.
    assert SALES_QUOTE.display_total in replies[-1]


def test_the_intake_advances_across_separate_deliveries(service, storefront, db):
    """The failure a single-message test cannot see.

    A messenger carries no session. If the scope were not written back to the
    conversation, every delivery would re-ask question one and the buyer would
    answer the same question forever.
    """
    from tests.test_checkout import INTAKE_ANSWERS

    asked = walk_the_intake(service, storefront, INTAKE_ANSWERS[:3])

    # Three distinct questions, not the same one three times.
    questions = [line for line in asked if line.strip().endswith("?")]
    assert len(set(questions)) == len(questions)

    scope = db.query(Conversation).one().scope_json
    assert scope, "the intake answers were not remembered between deliveries"


def test_a_telegram_price_is_backed_by_a_redeemable_quote(service, storefront, db):
    """A number on a phone that no checkout can re-derive is not a price.

    Telegram has no payment step of its own yet. What it must not do is quote a
    figure that exists only in a chat log — the quote behind it has to be the
    same stored, recomputable row the web checkout redeems.
    """
    from app.pricing.quotes import QuoteService, reference_from_plan_code
    from tests.test_checkout import INTAKE_ANSWERS, SALES_QUOTE

    walk_the_intake(service, storefront, INTAKE_ANSWERS)

    code = db.query(Conversation).one().interested_plan_code
    reference = reference_from_plan_code(code)
    assert reference, f"no quote reference behind the quoted price: {code!r}"

    # Recomputed from the stored requirement, not read back from the row, so
    # this also asserts the requirement itself survived the channel.
    _row, recomputed = QuoteService(db).recompute(reference)
    assert recomputed.total_minor == SALES_QUOTE.total_minor


def test_the_same_answers_cost_the_same_on_telegram_and_whatsapp(
    service, storefront, db
):
    """Two channels, one price. The cheapest guard against a per-channel fork."""
    from tests.test_checkout import INTAKE_ANSWERS

    def quoted_figure(channel, external_id):
        replies = []
        for answer in INTAKE_ANSWERS:
            replies.extend(
                service.handle(
                    storefront.id,
                    inbound(answer, channel=channel, external_id=external_id),
                ).replies
            )
        return replies[-1]

    on_telegram = quoted_figure(CHANNEL_TELEGRAM, "111")
    on_whatsapp = quoted_figure(CHANNEL_WHATSAPP, "222")

    assert on_telegram == on_whatsapp


# ---------- advice and multi-select, on the pipe rather than in the agent ----------
#
# The advisor and the two-product order were built in ``app.sales.advisor`` and
# ``app.sales.scoping``, which the messaging service never imports. That is the
# design — one engine, and the messenger composes no product sentences of its own
# — but "it should inherit it" is exactly the kind of claim that is true right up
# until a channel grows a shortcut. So these walk it over the pipe.


def test_a_telegram_buyer_who_describes_their_business_is_advised_first(
    service, storefront, db
):
    """The consultative turn, on a phone.

    A buyer who opens with what they do gets told which of the catalog fits and
    why, before any figure. If this came back as the raw intake question, the
    messenger would be the channel where Nera asks someone to choose between
    products it never explained.
    """
    reply = service.handle(
        storefront.id, inbound("I run a food store in Ijebu Ode")
    ).replies[-1]

    assert "AI Sales Representative" in reply
    assert "₦" not in reply, "advice comes before pricing, not with it"


def test_advice_over_a_messenger_does_not_choose_for_the_buyer(
    service, storefront, db
):
    """A recommendation written into the scope is a product nobody picked.

    Worse on a messenger than in a browser: there is no page to re-read, so the
    first the buyer would know of it is the total.
    """
    service.handle(storefront.id, inbound("I run a food store"))

    conversation = db.query(Conversation).one()
    scope = conversation.scope_json or ""

    assert "sales_agent" not in scope, "the advice selected a product by itself"


def test_a_business_we_cannot_help_is_escalated_from_telegram_too(
    service, storefront, db
):
    """The refusal and the approval row, both, on the channel a buyer used.

    A need outside the catalog answered on Telegram with an encouraging greeting
    is the same claim we refuse to make on the web — and there is a human whose
    attention it is worth.
    """
    reply = service.handle(
        storefront.id,
        inbound("I need an AI that does my bookkeeping and files my taxes"),
    ).replies[-1]

    assert "right fit" in reply
    assert db.query(ApprovalRequest).count() == 1


def test_a_telegram_buyer_can_take_both_products_in_one_order(
    service, storefront, db
):
    """Two products, one walk, one price — over the pipe.

    The specific failure this catches: the multi-select answer is parsed in
    scoping, but the *scope* has to survive the conversation row between
    deliveries as a list rather than a single value. If it narrowed to one
    product on the way to storage, this buyer would be quoted for one agent
    having asked for two, and nothing before the payment page would say so.
    """
    from app.pricing.complexity import (
        CHANNEL_WEB,
        CHANNEL_WHATSAPP,
        PRODUCT_SALES_AGENT,
        PRODUCT_SUPPORT_AGENT,
        Requirement,
        price,
    )

    expected = price(
        Requirement(
            products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT),
            channels=(CHANNEL_WEB, CHANNEL_WHATSAPP),
            monthly_conversations=2000,
            integrations=(),
        )
    )

    replies = walk_the_intake(
        service,
        storefront,
        ("both", "my website and whatsapp", "about 2,000 a month", "none"),
    )

    conversation = db.query(Conversation).one()
    assert conversation.stage == "ready_to_buy"

    quoted = replies[-1]
    assert expected.display_total in quoted

    # Both names in the message that reached the phone. A bundle total with only
    # one product named reads as a single agent that costs too much.
    assert "AI Sales Representative" in quoted
    assert "AI Support Agent" in quoted


def test_a_two_product_telegram_quote_is_redeemable_for_both(service, storefront, db):
    """What the buyer pays for has to be what provisioning reads.

    The figure on the phone is only half of it. The stored requirement is what
    the checkout re-prices and what provisioning reads to decide how many agents
    to stand up, so if the second product did not survive the channel the buyer
    would pay for two and be given one — with every internal signal reading
    "delivered".
    """
    from app.pricing.complexity import PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT
    from app.pricing.quotes import QuoteService, reference_from_plan_code

    walk_the_intake(
        service,
        storefront,
        ("both", "my website and whatsapp", "about 2,000 a month", "none"),
    )

    code = db.query(Conversation).one().interested_plan_code
    reference = reference_from_plan_code(code)
    assert reference, f"no quote reference behind the quoted price: {code!r}"

    _row, recomputed = QuoteService(db).recompute(reference)

    assert recomputed.products == (PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT)


def test_two_products_cost_the_same_on_telegram_and_whatsapp(
    service, storefront, db
):
    """The parity guard, for the order shape that is new.

    The single-product version of this passes today. A bundle is where a
    per-channel fork would show up first, because it is the path with the least
    traffic over it.
    """
    answers = ("both", "just my website", "about 2,000 a month", "none")

    def quoted_figure(channel, external_id):
        replies = []
        for answer in answers:
            replies.extend(
                service.handle(
                    storefront.id,
                    inbound(answer, channel=channel, external_id=external_id),
                ).replies
            )
        return replies[-1]

    assert quoted_figure(CHANNEL_TELEGRAM, "333") == quoted_figure(
        CHANNEL_WHATSAPP, "444"
    )


def test_the_product_question_on_a_messenger_lists_the_whole_catalog(
    service, storefront, db
):
    """Whatever we can price, a messenger buyer is offered.

    The question is generated from the catalog, so a product added to pricing
    appears here without anyone editing a channel. This asserts that rather than
    trusting it.
    """
    from app.pricing.complexity import PRODUCT_NAMES

    reply = service.handle(storefront.id, inbound("how much does it cost?")).replies[-1]

    for name in PRODUCT_NAMES.values():
        assert name in reply, f"{name} is priceable but never offered on Telegram"


def test_no_retired_tier_can_be_bought_over_a_messenger(service, storefront, db):
    """The tiers are gone from the storefront. Asking for one by name on
    Telegram must not resurrect it — that would make the messenger the one
    channel where a withdrawn price is still for sale."""
    handled = service.handle(
        storefront.id, inbound("I'll take the Founding User plan, 180,000")
    )

    body = " ".join(handled.replies)

    assert "180,000" not in body
    assert db.query(Conversation).one().interested_plan_code is None
