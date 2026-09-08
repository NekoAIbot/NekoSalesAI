"""Post-payment delivery: does the buyer find out?

This file exists because of a sale where every other test in the suite would
have passed. A real buyer paid ₦148,000 on Telegram. Paystack took the money,
the order was verified, two agents were provisioned into a live workspace, and
the credentials email was queued. The buyer, sitting in the Telegram thread they
had bought from, was told nothing at all — and the tests were happy, because
every one of them asserted on database state rather than on whether a message
reached a person.

So the assertions here are deliberately about the buyer's end. Not "was the
order paid", not "was a profile created" — those already passed while the bug
was live. What matters is: is there a message, does it say the true thing, did
it go out on the channel the buyer actually used, and does it go out exactly
once no matter how many times the reconciler runs.

Everything runs against a fake Paystack transport and a fake chat client, which
is what makes the awkward cases reachable: a payment confirmed while nobody is
looking, a delivery attempted twice, a chat platform that is down at the moment
the money lands.
"""

import pytest

from app.models.channel_identity import ChannelIdentity
from app.models.conversation import ROLE_AGENT, Conversation, Message
from app.models.order import Order
from app.models.organization import Organization
from app.messaging.clients import MESSAGE_LIMIT
from app.payments.checkout import CheckoutService
from app.payments.delivery import (
    RULE_DELIVERED,
    DeliveryPusher,
    DeliveryService,
    Push,
    compose_delivery,
    delivery_parts,
)
from app.payments.paystack import PaystackClient
from app.payments.provisioning import ProvisioningService
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT

from tests.test_checkout import (
    BOTH_PRODUCTS_BUILD,
    SALES_BUILD,
    TEST_SECRET,
    FakeTransport,
    make_order,
)


# ---------- fixtures ----------


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def paystack(transport) -> PaystackClient:
    return PaystackClient(secret_key=TEST_SECRET, transport=transport)


@pytest.fixture
def storefront(db) -> Organization:
    from app.config.settings import settings

    org = Organization(name="NekoSalesAI Demo", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def checkout(db, paystack) -> CheckoutService:
    return CheckoutService(db, client=paystack)


class FakeChat:
    """A chat platform that records instead of sending."""

    def __init__(self, fails: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fails = fails

    def send_message(self, chat_id: str, text: str) -> None:
        if self.fails:
            raise RuntimeError("platform unreachable")

        self.sent.append((chat_id, text))


def telegram_thread(db, storefront, chat_id: str = "6851150519") -> Conversation:
    """A conversation that came in over Telegram, as the poller creates one."""
    conversation = Conversation(
        organization_id=storefront.id,
        public_token=f"tok-{chat_id}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    db.add(
        ChannelIdentity(
            organization_id=storefront.id,
            channel="telegram",
            external_id=chat_id,
            conversation=conversation,
        )
    )
    db.commit()

    return conversation


def web_thread(db, storefront) -> Conversation:
    """A conversation with no chat platform behind it — a website visitor."""
    conversation = Conversation(
        organization_id=storefront.id,
        public_token="tok-web-visitor",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def pay(checkout, transport, order: Order) -> Order:
    """Confirm an order the way a server-to-server verification does.

    The amount is echoed back from the order because the fake defaults to the
    single-product price, and an amount mismatch is refused by design — a
    two-product order confirmed against a one-product figure would look like
    tampering, which is exactly what that check is for.
    """
    transport.paid = True
    transport.amount_override = order.amount_minor
    return checkout.confirm_by_reference(order.paystack_reference)


def bought(db, checkout, transport, storefront, conversation, build=None) -> Order:
    """A paid, provisioned order attached to a conversation. The starting point."""
    order = make_order(
        checkout,
        storefront,
        build=build or SALES_BUILD,
        conversation=conversation,
    )
    order = pay(checkout, transport, order)
    ProvisioningService(db).provision(order)
    return order


def delivery_messages(db, conversation_id: int) -> list[Message]:
    return [
        message
        for message in db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .all()
        if RULE_DELIVERED in (message.reasoning_json or "")
    ]


# ---------- the message itself ----------


def test_the_confirmation_leads_with_the_amount(db, checkout, transport, storefront):
    """What a buyer wants first is proof the right amount left their account."""
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    text = compose_delivery(order, DeliveryService(db).profiles_for(order))

    assert text.splitlines()[0].startswith("Payment confirmed")
    assert "₦" in text


def test_the_confirmation_names_every_agent_that_was_built(
    db, checkout, transport, storefront
):
    """Two products bought means two agents named, not a vague plural."""
    conversation = web_thread(db, storefront)
    order = make_order(
        checkout,
        storefront,
        build=BOTH_PRODUCTS_BUILD,
        conversation=conversation,
    )
    order = pay(checkout, transport, order)
    result = ProvisioningService(db).provision(order)

    text = compose_delivery(order, list(result.profiles))

    assert len(result.profiles) == 2

    for profile in result.profiles:
        assert profile.agent_name in text


def test_the_confirmation_never_contains_a_credential(
    db, checkout, transport, storefront
):
    """The one thing this message must not do.

    At the moment provisioning runs, the API key and temporary password are in
    memory and could be pasted straight into the thread. A chat log is forwarded,
    screenshotted and synced to places the buyer does not control, and a secret
    posted into one cannot be unposted. So the message says where the credentials
    are rather than what they are, and this test is what stops a future edit
    deciding that is unhelpful.
    """
    conversation = telegram_thread(db, storefront)
    order = make_order(checkout, storefront, conversation=conversation)
    order = pay(checkout, transport, order)
    result = ProvisioningService(db).provision(order)

    text = compose_delivery(order, list(result.profiles))

    assert result.api_key
    assert result.temporary_password
    assert result.api_key not in text
    assert result.temporary_password not in text


def test_the_confirmation_says_the_one_next_step(db, checkout, transport, storefront):
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    text = compose_delivery(order, DeliveryService(db).profiles_for(order))

    assert "widget" in text.lower()
    assert order.buyer_email in text


def test_the_amount_is_formatted_like_money(db, checkout, transport, storefront):
    """"₦ 31,000" was what the first line said. The space is not how money reads."""
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    text = compose_delivery(order, DeliveryService(db).profiles_for(order))

    assert "₦ " not in text
    assert "NGN" not in text


def test_the_buyer_is_sent_to_a_page_that_exists(
    db, checkout, transport, storefront
):
    """The sign-in link was ``/dashboard``, and the only route is ``/desk``.

    Two messages disagreed about it — the credentials email said ``/desk`` and
    this one said ``/dashboard`` — so a customer who followed the chat message
    landed on a 404 immediately after paying. Both now come from one function.
    """
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    text = compose_delivery(order, DeliveryService(db).profiles_for(order))

    assert "/desk" in text
    assert "/dashboard" not in text


# ---------- the instructions, which are the point of the message ----------


def test_the_buyer_is_given_the_actual_snippet_not_told_one_exists(
    db, checkout, transport, storefront
):
    """"Paste your widget snippet into your site" is not an instruction.

    It names the task and none of the doing. Someone who has just paid does not
    know where the snippet lives or what ``</body>`` means, and that gap is where
    a paying customer quietly gives up. The token is safe in chat — it ends up in
    page source by design — so the copy-pasteable thing goes in the message.
    """
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    profiles = DeliveryService(db).profiles_for(order)
    text = compose_delivery(order, profiles)

    assert profiles[0].widget_token
    assert profiles[0].widget_token in text
    assert "<script" in text
    assert "</body>" in text


def test_every_platform_a_buyer_might_be_on_gets_its_own_route(
    db, checkout, transport, storefront
):
    """Named menus, not "edit your theme".

    A step someone cannot follow while looking at their own screen is not a step,
    so each platform is described in the words its own admin uses.
    """
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    text = compose_delivery(order, DeliveryService(db).profiles_for(order))

    assert "WordPress" in text
    assert "Shopify" in text
    assert "theme.liquid" in text
    assert "Code Injection" in text
    assert "Footer" in text


def test_the_closing_line_does_not_default_to_fetching_a_human(
    db, checkout, transport, storefront
):
    """The first message after payment teaches the customer what to expect.

    It used to promise "I will get a person on it", which sets the expectation
    that problems here are solved by escalation. That is the opposite of what is
    being sold. The offer of a person stays — a customer who needs one should not
    have to fight for it — but it is no longer the default.
    """
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    text = compose_delivery(order, DeliveryService(db).profiles_for(order))

    assert "I will get a person on it" not in text
    assert "walk you through it" in text
    assert "genuinely cannot help with directly" in text


def test_two_agents_get_two_labelled_snippets(db, checkout, transport, storefront):
    """One snippet plus "repeat for the other" is how the same agent ends up twice."""
    conversation = web_thread(db, storefront)
    order = make_order(
        checkout,
        storefront,
        build=BOTH_PRODUCTS_BUILD,
        conversation=conversation,
    )
    order = pay(checkout, transport, order)
    result = ProvisioningService(db).provision(order)

    text = compose_delivery(order, list(result.profiles))

    for profile in result.profiles:
        assert profile.widget_token in text
        assert profile.agent_name in text


def test_a_buyer_who_bought_telegram_is_told_about_telegram(
    db, checkout, transport, storefront
):
    """Channels are priced, so they have to be addressed.

    Telegram costs ₦4,000 extra. A delivery message that talks only about a
    website snippet has taken money for something it did not mention again.
    """
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    profiles = DeliveryService(db).profiles_for(order)

    with_telegram = compose_delivery(order, profiles, channels=("web", "telegram"))
    without = compose_delivery(order, profiles, channels=("web",))

    assert "BotFather" in with_telegram
    assert "BotFather" not in without


def test_the_telegram_note_never_asks_for_a_token_in_chat(
    db, checkout, transport, storefront
):
    """A bot token is a bearer credential for the whole bot.

    The same rule as the API key: a chat log is forwarded and screenshotted, and
    a token posted into one cannot be unposted. So the instructions stop at
    "you now have a token" and explicitly tell the customer not to paste it.
    """
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    text = compose_delivery(
        order,
        DeliveryService(db).profiles_for(order),
        channels=("telegram",),
    )

    assert "Do not paste that token here" in text


def test_channels_are_read_back_from_what_was_actually_bought(
    db, checkout, transport, storefront
):
    """Not from a guess, and not from the order — from the priced requirement."""
    conversation = web_thread(db, storefront)
    order = make_order(
        checkout,
        storefront,
        build=BOTH_PRODUCTS_BUILD,
        conversation=conversation,
    )
    order = pay(checkout, transport, order)
    ProvisioningService(db).provision(order)

    channels = DeliveryService(db).channels_for(order)

    assert set(channels) == set(BOTH_PRODUCTS_BUILD.channels)


def test_an_unreadable_quote_still_delivers(db, checkout, transport, storefront):
    """Fewer paragraphs is a fine outcome. A failed delivery is not."""
    conversation = telegram_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    order.plan_code = "quote_nothing_by_this_name"
    db.commit()

    assert DeliveryService(db).channels_for(order) == ()
    assert DeliveryService(db).deliver(order)


# ---------- delivering it ----------


def test_a_paid_order_puts_a_message_in_the_conversation(
    db, checkout, transport, storefront
):
    """The web surface reads messages, so the rows are the delivery."""
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    pushes = DeliveryService(db).deliver(order)

    assert pushes == []

    messages = delivery_messages(db, conversation.id)

    # Several messages, because full install guidance does not fit in one that a
    # chat platform will accept — but exactly one of them announces the payment.
    assert len(messages) > 1
    assert all(message.role == ROLE_AGENT for message in messages)
    assert messages[0].body.startswith("Payment confirmed")
    assert sum("Payment confirmed" in m.body for m in messages) == 1


def test_a_telegram_buyer_is_pushed_to_on_telegram(
    db, checkout, transport, storefront
):
    """The bug, in one assertion. This is what the live sale did not do."""
    conversation = telegram_thread(db, storefront, chat_id="6851150519")
    order = bought(db, checkout, transport, storefront, conversation)

    pushes = DeliveryService(db).deliver(order)

    assert pushes
    assert {push.channel for push in pushes} == {"telegram"}
    assert {push.external_id for push in pushes} == {"6851150519"}
    assert "Payment confirmed" in pushes[0].text

    # And the transcript records what was sent, so the thread reads correctly
    # next time anyone — buyer or support — opens it.
    assert [push.text for push in pushes] == [
        message.body for message in delivery_messages(db, conversation.id)
    ]


def test_no_single_delivery_message_is_too_long_to_send(
    db, checkout, transport, storefront
):
    """A rejected send looks exactly like a chat platform being down.

    Telegram refuses a sendMessage over 4,096 characters and WhatsApp refuses the
    same figure, and the refusal is logged and swallowed — so a delivery that grew
    past the limit would strand the buyer while every counter said it had gone
    out. Install guidance is long enough for this to be a live risk rather than a
    theoretical one, which is why it is composed as parts.
    """
    conversation = telegram_thread(db, storefront)
    order = make_order(
        checkout,
        storefront,
        build=BOTH_PRODUCTS_BUILD,
        conversation=conversation,
    )
    order = pay(checkout, transport, order)
    ProvisioningService(db).provision(order)

    pushes = DeliveryService(db).deliver(order)

    assert pushes
    assert all(len(push.text) <= MESSAGE_LIMIT for push in pushes)


def test_delivery_is_stamped_on_the_order(db, checkout, transport, storefront):
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    assert not order.is_delivered

    DeliveryService(db).deliver(order)

    assert order.is_delivered
    assert order.delivered_at is not None


def test_a_buyer_is_told_once_however_many_passes_run(
    db, checkout, transport, storefront
):
    """Both the status poll and the reconciler call this, repeatedly.

    The confirmation page polls every couple of seconds and the poller reconciles
    every cycle, so "called twice" is the normal case rather than an edge one. A
    buyer receiving the same confirmation forty times is the failure this guards.
    """
    conversation = telegram_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    service = DeliveryService(db)

    first = service.deliver(order)
    second = service.deliver(order)
    third = service.deliver(order)

    assert first
    assert second is None
    assert third is None
    assert sum(
        "Payment confirmed" in message.body
        for message in delivery_messages(db, conversation.id)
    ) == 1


def test_an_unpaid_order_is_never_delivered(db, checkout, storefront):
    """Saying "payment confirmed" before it is, is worse than saying nothing."""
    conversation = web_thread(db, storefront)
    order = make_order(checkout, storefront, conversation=conversation)

    assert DeliveryService(db).deliver(order) is None
    assert not delivery_messages(db, conversation.id)


def test_a_paid_order_with_nothing_provisioned_yet_waits(
    db, checkout, transport, storefront
):
    """"Your workspace is live" must not be said before it is.

    This is the same lie as the spinner that started all of it, just in the other
    direction — and the next pass will deliver, so waiting costs seconds.
    """
    conversation = web_thread(db, storefront)
    order = make_order(checkout, storefront, conversation=conversation)
    order = pay(checkout, transport, order)

    assert DeliveryService(db).deliver(order) is None
    assert not order.is_delivered


# ---------- reconciling without a webhook ----------


def test_reconcile_notices_a_payment_nobody_told_us_about(
    db, checkout, transport, storefront
):
    """The whole point of the reconciler.

    There is no public HTTPS URL on this deployment, so Paystack cannot call in.
    A buyer taps the checkout link, pays in another tab and sends no further
    message — nothing arrives to trigger anything. Asking is the only way the
    payment is ever known.
    """
    conversation = telegram_thread(db, storefront)
    order = make_order(checkout, storefront, conversation=conversation)

    # Paystack now says paid. Nothing has told us.
    transport.paid = True
    transport.amount_override = order.amount_minor

    report = DeliveryService(db, checkout=checkout).reconcile()

    assert report.newly_paid == 1
    assert report.provisioned == 1
    assert report.delivered == 1
    assert {push.channel for push in report.pushes} == {"telegram"}

    db.refresh(order)
    assert order.is_paid
    assert order.is_delivered


def test_reconcile_provisions_what_the_payment_bought(
    db, checkout, transport, storefront
):
    """Delivery is not just a message: the thing being announced must exist."""
    conversation = telegram_thread(db, storefront)
    order = make_order(
        checkout,
        storefront,
        build=BOTH_PRODUCTS_BUILD,
        conversation=conversation,
    )
    transport.paid = True
    transport.amount_override = order.amount_minor

    DeliveryService(db, checkout=checkout).reconcile()

    db.refresh(order)
    roles = {profile.role for profile in DeliveryService(db).profiles_for(order)}

    assert roles == {ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT}


def test_reconcile_leaves_an_unpaid_order_alone(db, checkout, transport, storefront):
    conversation = telegram_thread(db, storefront)
    order = make_order(checkout, storefront, conversation=conversation)

    transport.paid = False
    transport.amount_override = order.amount_minor

    report = DeliveryService(db, checkout=checkout).reconcile()

    assert report.newly_paid == 0
    assert report.delivered == 0
    assert not delivery_messages(db, conversation.id)


def test_reconcile_is_quiet_when_there_is_nothing_to_do(db, storefront):
    report = DeliveryService(db, checkout=checkout).reconcile()

    assert report.quiet
    assert report.ok
    assert report.delivered == 0


def test_reconcile_catches_up_an_order_paid_before_this_existed(
    db, checkout, transport, storefront
):
    """The buyers who were already stranded.

    Two real orders were paid and provisioned while delivery did not exist, so
    ``delivered_at`` is null for them and that is the truth — they were never
    told. The first pass after this ships should tell them, once.
    """
    conversation = telegram_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    assert not order.is_delivered

    report = DeliveryService(db, checkout=checkout).reconcile(verify_pending=False)

    assert report.delivered == 1
    assert report.pushes
    assert {push.channel for push in report.pushes} == {"telegram"}

    # And not again on the next pass.
    assert DeliveryService(db, checkout=checkout).reconcile(verify_pending=False).delivered == 0


def test_one_failing_order_does_not_strand_the_others(
    db, checkout, transport, storefront, monkeypatch
):
    """A reconcile pass handles every buyer or none, and none is unacceptable."""
    first = telegram_thread(db, storefront, chat_id="111")
    second = telegram_thread(db, storefront, chat_id="222")

    bad = bought(db, checkout, transport, storefront, first)
    good = bought(db, checkout, transport, storefront, second)

    real = DeliveryService.deliver

    def explode(self, order):
        if order.id == bad.id:
            raise RuntimeError("something went wrong for this one buyer")

        return real(self, order)

    monkeypatch.setattr(DeliveryService, "deliver", explode)

    report = DeliveryService(db, checkout=checkout).reconcile(verify_pending=False)

    assert report.delivered == 1
    assert not report.ok
    assert any(bad.paystack_reference in error for error in report.errors)

    db.refresh(good)
    assert good.is_delivered


# ---------- getting it onto the platform ----------


def test_the_pusher_sends_to_the_chat_it_was_given():
    chat = FakeChat()
    pusher = DeliveryPusher({"telegram": chat})

    sent = pusher.send_all([Push(channel="telegram", external_id="42", text="live")])

    assert sent == 1
    assert chat.sent == [("42", "live")]


def test_a_platform_that_is_down_does_not_raise():
    """The order is already delivered as far as the database is concerned.

    Raising here would propagate into the poll loop or a checkout request, and
    cost every buyer to punish one unreachable chat. The transcript row is
    written and the credentials email is the durable copy, so a failed push costs
    a notification rather than the thing that was bought.
    """
    pusher = DeliveryPusher({"telegram": FakeChat(fails=True)})

    assert pusher.send_all([Push(channel="telegram", external_id="42", text="hi")]) == 0


def test_a_channel_with_no_client_is_reported_not_crashed():
    pusher = DeliveryPusher({"telegram": FakeChat()})

    assert pusher.send_all([Push(channel="whatsapp", external_id="+234", text="hi")]) == 0
