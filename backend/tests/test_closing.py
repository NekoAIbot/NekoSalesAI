"""The close: a conversation that reached a price becoming a link that can be paid.

The bug these exist for was found by walking a real Telegram conversation rather
than by a failing test — which is why they are here now. Nera finished a whole
intake, quoted ₦31,000, took the buyer's name, email and company, said "I'm
raising it now", and then nothing happened. No link, no order, no error. The
buyer had done everything asked of them and had no way to pay.

It looked like a closed deal from the inside: the stage was ``ready_to_buy``, the
quote was stored, the lead was recorded. Every internal signal said "sold". Only
the buyer knew otherwise, and they had nothing to go on but silence.

So the properties pinned here are the ones whose absence is invisible:

*A close produces a link.* Not a stage, not a stored quote — something a buyer
can open.

*The amount on it is the engine's.* Re-derived by the checkout from the stored
requirement, never carried from the chat.

*It happens once.* A link repeated every turn is an agent pestering someone.

*What was sent is in the transcript.* Otherwise the most consequential message
in the conversation exists only in a chat app a reviewer cannot see.

*Failure is spoken.* Every way this can fail says so, because silence is exactly
what made the original bug expensive.
"""

import pytest

from app.messaging.inbound import COMMAND_PAY, KIND_COMMAND, KIND_TEXT, InboundMessage
from app.messaging.service import InboundMessagingService
from app.models.channel_identity import CHANNEL_TELEGRAM, CHANNEL_WHATSAPP
from app.models.conversation import Conversation, Message
from app.models.order import ORDER_PAID, ORDER_PENDING, Order
from app.models.organization import Organization
from app.payments import PaystackClient
from app.payments.checkout import CheckoutService
from app.sales.closing import RULE_PAYMENT_BLOCKED, RULE_PAYMENT_LINK, ClosingService
from tests.test_checkout import INTAKE_ANSWERS, SALES_QUOTE, TEST_SECRET, FakeTransport


@pytest.fixture
def storefront(db):
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
def transport():
    return FakeTransport()


@pytest.fixture
def service(db, transport):
    """The messaging service with a Paystack that answers but charges nothing."""
    messaging = InboundMessagingService(
        db, telegram=FakeClient(), whatsapp=FakeClient()
    )
    messaging.closing = ClosingService(
        db,
        checkout=CheckoutService(
            db, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
        ),
    )

    return messaging


_counter = {"n": 0}


def inbound(text, *, channel=CHANNEL_TELEGRAM, external_id="4242", kind=KIND_TEXT,
            command=""):
    _counter["n"] += 1

    return InboundMessage(
        channel=channel,
        external_id=external_id,
        delivery_id=f"tg:{_counter['n']}",
        kind=kind,
        text=text,
        command=command,
        sender_name="Ada Nwosu",
    )


# The turns that take a buyer from hello to handing over their details. The last
# one is what the agent asks for at the close, in the shape a person types it.
TO_THE_CLOSE = (
    *INTAKE_ANSWERS,
    "yes that works",
    "Ada Nwosu, Bright Dental, ada@brightdental.example",
)


def buy(service, storefront, turns=TO_THE_CLOSE, channel=CHANNEL_TELEGRAM,
        external_id="4242"):
    """Walk a buyer to the close and return everything they were sent."""
    replies = []

    for text in turns:
        replies.extend(
            service.handle(
                storefront.id, inbound(text, channel=channel, external_id=external_id)
            ).replies
        )

    return replies


# ---------- the bug itself ----------


def test_a_messenger_buyer_is_given_something_they_can_pay(
    service, storefront, db
):
    """The regression, stated as plainly as it can be.

    Before this, the conversation ended here and the buyer was never sent a
    link. The stage said sold; the buyer had nothing.
    """
    replies = buy(service, storefront)

    order = db.query(Order).one()

    assert order.checkout_url
    assert order.checkout_url in replies[-1]


def test_the_amount_charged_is_the_amount_the_engine_derived(
    service, storefront, db, transport
):
    """The figure quoted in the chat and the figure sent to Paystack are one
    number, computed once, in the pricing engine."""
    buy(service, storefront)

    initialize = [
        r for r in transport.requests if "/transaction/initialize" in r["url"]
    ]

    assert len(initialize) == 1
    assert initialize[0]["body"]["amount"] == SALES_QUOTE.total_minor
    assert db.query(Order).one().amount_minor == SALES_QUOTE.total_minor


def test_the_order_carries_the_details_read_out_of_the_conversation(
    service, storefront, db
):
    """A close nobody can follow up is half a sale."""
    buy(service, storefront)

    order = db.query(Order).one()

    assert order.buyer_email == "ada@brightdental.example"
    assert order.buyer_name == "Ada Nwosu"
    assert order.buyer_company == "Bright Dental"
    assert order.conversation_id == db.query(Conversation).one().id


def test_the_link_reaches_whatsapp_too(service, storefront, db):
    """One close, every channel. A payment path that only worked on Telegram
    would be a second implementation waiting to drift."""
    replies = buy(service, storefront, channel=CHANNEL_WHATSAPP, external_id="234801")

    assert db.query(Order).one().checkout_url in replies[-1]


# ---------- once, and only once ----------


def test_the_link_is_not_repeated_on_every_later_turn(service, storefront, db):
    """An agent that re-sends a payment link after every message stops reading
    as helpful and starts reading as a machine asking for money."""
    buy(service, storefront)
    url = db.query(Order).one().checkout_url

    after = service.handle(storefront.id, inbound("thanks")).replies

    assert url not in " ".join(after)
    assert db.query(Order).count() == 1


def test_carrying_on_talking_does_not_stack_orders(service, storefront, db):
    """Several more turns at the close, still one order."""
    buy(service, storefront)

    for text in ("thanks", "what does it include", "and support?"):
        service.handle(storefront.id, inbound(text))

    assert db.query(Order).count() == 1


# ---------- asking for it again ----------


def test_pay_brings_the_link_back(service, storefront, db):
    """On a messenger a link is a message in a thread, not a page that can be
    refreshed. A buyer who scrolled past it needs a way to ask again."""
    buy(service, storefront)
    url = db.query(Order).one().checkout_url

    again = service.handle(
        storefront.id, inbound("/pay", kind=KIND_COMMAND, command=COMMAND_PAY)
    ).replies

    assert url in again[0]
    assert db.query(Order).count() == 1, "asking again raised a second order"


def test_pay_before_there_is_anything_to_buy_says_so(service, storefront, db):
    """Silence would leave the buyer unable to tell a broken bot from one that
    is waiting on them."""
    replies = service.handle(
        storefront.id, inbound("/pay", kind=KIND_COMMAND, command=COMMAND_PAY)
    ).replies

    assert replies, "/pay was answered with nothing at all"
    assert "nothing to pay for yet" in replies[-1].lower()
    assert db.query(Order).count() == 0


def test_pay_mid_intake_does_not_raise_a_payment(service, storefront, db):
    """A buyer three questions in has not agreed to a figure. Sending them a
    live link would be asking for money for something they never said yes to."""
    buy(service, storefront, turns=INTAKE_ANSWERS[:3])

    service.handle(
        storefront.id, inbound("/pay", kind=KIND_COMMAND, command=COMMAND_PAY)
    )

    assert db.query(Order).count() == 0


def test_help_mentions_the_command(service, storefront):
    """An undiscoverable command is not a feature."""
    from app.messaging.inbound import COMMAND_HELP

    replies = service.handle(
        storefront.id, inbound("/help", kind=KIND_COMMAND, command=COMMAND_HELP)
    ).replies

    assert "/pay" in " ".join(replies)


# ---------- the transcript a human reviews ----------


def test_the_link_is_in_the_transcript(service, storefront, db):
    """The most consequential message in the conversation must not exist only
    inside a chat app."""
    buy(service, storefront)
    url = db.query(Order).one().checkout_url

    bodies = [m.body for m in db.query(Message).all()]

    assert any(url in body for body in bodies)


def test_the_link_message_carries_its_reasoning(service, storefront, db):
    """Every other reply says why it was sent. This one carries the most money,
    so it says so too."""
    buy(service, storefront)

    reasoned = [
        m for m in db.query(Message).all()
        if m.reasoning_json and RULE_PAYMENT_LINK in m.reasoning_json
    ]

    assert len(reasoned) == 1
    assert db.query(Order).one().paystack_reference in reasoned[0].reasoning_json


# ---------- when it cannot be done ----------


def test_payments_switched_off_is_explained_not_swallowed(db, storefront):
    """A deployment with no Paystack key must not silently drop the close.

    This is the exact shape of the original bug — everything internal says sold
    and the buyer hears nothing — so it is asserted against directly.
    """
    from app.payments.paystack import PaymentsNotConfigured

    class Unconfigured:
        def create_order(self, **kwargs):
            raise PaymentsNotConfigured("PAYSTACK_SECRET_KEY is not set")

    messaging = InboundMessagingService(
        db, telegram=FakeClient(), whatsapp=FakeClient()
    )
    messaging.closing = ClosingService(db, checkout=Unconfigured())

    replies = buy(messaging, storefront)

    assert replies, "the close produced no message at all"
    said = replies[-1].lower()

    # Names what happens next, and does not blame the buyer or ask them to retry
    # into something that cannot work.
    assert "someone will send you the link" in said
    assert db.query(Order).count() == 0


def test_a_provider_outage_says_nothing_was_charged(db, storefront):
    """The one fact a buyer most needs after a failed payment attempt."""
    from app.payments.paystack import PaystackError

    class Down:
        def create_order(self, **kwargs):
            raise PaystackError("gateway timeout")

    messaging = InboundMessagingService(
        db, telegram=FakeClient(), whatsapp=FakeClient()
    )
    messaging.closing = ClosingService(db, checkout=Down())

    replies = buy(messaging, storefront)

    assert "nothing has been charged" in replies[-1].lower()


def test_an_order_with_no_link_is_not_reported_as_a_close(db, storefront):
    """A message with a blank where the link should be is worse than an
    explanation."""
    class NoUrl:
        def create_order(self, **kwargs):
            return Order(
                organization_id=storefront.id,
                paystack_reference="neko_nolink",
                plan_code="quote_x",
                plan_name="AI Sales Representative",
                billing_period="month",
                amount_minor=SALES_QUOTE.total_minor,
                currency="NGN",
                buyer_email="ada@brightdental.example",
                status=ORDER_PENDING,
                checkout_url=None,
            )

    messaging = InboundMessagingService(
        db, telegram=FakeClient(), whatsapp=FakeClient()
    )
    messaging.closing = ClosingService(db, checkout=NoUrl())

    replies = buy(messaging, storefront)

    assert "didn't come back with a link" in replies[-1]
    assert "nothing has been charged" in replies[-1].lower()


def test_a_blocked_close_is_recorded_as_escalated(db, storefront):
    """A buyer stuck at the payment step is something a person should see."""
    from app.payments.paystack import PaymentsNotConfigured

    class Unconfigured:
        def create_order(self, **kwargs):
            raise PaymentsNotConfigured("no key")

    messaging = InboundMessagingService(
        db, telegram=FakeClient(), whatsapp=FakeClient()
    )
    messaging.closing = ClosingService(db, checkout=Unconfigured())

    buy(messaging, storefront)

    blocked = [
        m for m in db.query(Message).all()
        if m.reasoning_json and RULE_PAYMENT_BLOCKED in m.reasoning_json
    ]

    assert len(blocked) == 1
    assert '"escalated": true' in blocked[0].reasoning_json


# ---------- the service on its own ----------


def test_ready_is_false_until_the_stage_and_the_email_are_both_there(
    db, storefront
):
    from app.models.conversation import STAGE_QUALIFIED, STAGE_READY_TO_BUY

    conversation = Conversation(
        organization_id=storefront.id, public_token="t_x", stage=STAGE_QUALIFIED
    )
    conversation.interested_plan_code = "quote_qt_x"
    conversation.visitor_email = "ada@example.com"

    closing = ClosingService(db)
    assert closing.ready(conversation) is False

    conversation.stage = STAGE_READY_TO_BUY
    assert closing.ready(conversation) is True

    conversation.visitor_email = None
    assert closing.ready(conversation) is False


def test_a_paid_order_is_not_offered_as_a_pending_link(service, storefront, db):
    """Once it is paid, /pay must not hand back the same page again — the buyer
    would be looking at a checkout for something they already own."""
    buy(service, storefront)

    order = db.query(Order).one()
    order.status = ORDER_PAID
    db.commit()

    assert ClosingService(db).existing_link(db.query(Conversation).one()) is None


# ---------- a plan code that outlived its plan ----------


def test_a_retired_plan_code_is_not_treated_as_closeable(db, storefront):
    """Threads from before the fixed tiers were withdrawn are still at the close.

    Nine of them, in the live database, two at ``ready_to_buy`` holding
    ``founding_annual`` — a code no catalog contains any more. Every ingredient
    ``ready`` used to check for was present, so the thread read as closeable, the
    checkout could not resolve the code, and the buyer was handed the resulting
    error: "There is no plan with the code 'founding_annual'." An internal
    identifier, shown to a customer, on every turn forever.
    """
    from app.models.conversation import STAGE_READY_TO_BUY

    conversation = Conversation(
        organization_id=storefront.id,
        public_token="t_stale",
        stage=STAGE_READY_TO_BUY,
    )
    conversation.interested_plan_code = "founding_annual"
    conversation.visitor_email = "ada@example.com"
    db.add(conversation)
    db.commit()

    closing = ClosingService(db)

    assert closing.ready(conversation) is False
    # And nothing is said to the buyer about it — the turn goes back to the
    # agent, which re-scopes. A blocked message here would be the same dead end
    # in politer words.
    assert closing.close(conversation) is None
    assert db.query(Order).count() == 0


def test_a_live_quote_reference_at_the_close_is_still_honoured(db, storefront):
    """The guard must not take working threads down with the retired ones.

    A quote reference is trusted here on purpose — whether it is still live is
    ``QuoteService.redeem``'s question, and its failure is already written for a
    buyer to read. Only plan codes are checked, because theirs is not.
    """
    from app.models.conversation import STAGE_READY_TO_BUY

    conversation = Conversation(
        organization_id=storefront.id,
        public_token="t_live",
        stage=STAGE_READY_TO_BUY,
    )
    conversation.interested_plan_code = "quote_qt_0123456789abcdef01234567"
    conversation.visitor_email = "ada@example.com"

    assert ClosingService(db).ready(conversation) is True
