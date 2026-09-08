"""Where the support facts come from.

``app.sales.support`` is pure and testable, and that is exactly why it cannot be
trusted on its own: every claim it makes about a customer's workspace — the code
has never loaded, your agent has answered forty-one conversations, you paid for
Telegram and it isn't set up — is only as good as the lookup behind it. A
confident sentence built on a wrong fact is worse than a vague one, because the
customer acts on it.

So this file tests the lookup, and the sharpest test in it is about who is *not*
a customer. A provisioned workspace serves the customer's own end-customers, and
one of those typing "it's not working" is talking about a dress or a delivery.
Resolving the workspace from the conversation's organization would have handed
every one of those people install instructions for a chat widget they have never
heard of — on the customer's own site, in the customer's own agent's voice. The
link is deliberately narrow: the thread the purchase was made in, and nothing
else.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.conversation import Conversation
from app.models.organization import Organization
from app.models.workspace_profile import PROVISION_PENDING, WorkspaceProfile
from app.payments.provisioning import ProvisioningService
from app.pricing.complexity import (
    CHANNEL_TELEGRAM,
    CHANNEL_WEB,
    CHANNEL_WHATSAPP,
    PRODUCT_SALES_AGENT,
    Requirement,
)
from app.sales.agent import RULE_DIAGNOSED, RULE_SUPPORT_ESCALATED
from app.sales.service import ConversationService

from tests.test_checkout import BOTH_PRODUCTS_BUILD, SALES_BUILD, make_order
from tests.test_delivery import (  # noqa: F401 — fixtures used by name
    checkout,
    paystack,
    storefront,
    transport,
)
from tests.test_delivery import bought, pay, telegram_thread, web_thread


def facts_for(db, conversation):
    return ConversationService(db)._setup_facts(conversation)


# ---------------------------------------------------------------------------
# Who counts as a customer
# ---------------------------------------------------------------------------


def test_a_visitor_who_has_bought_nothing_has_no_setup_facts(db, storefront):
    """None, so the whole support path stays switched off for a prospect."""
    conversation = web_thread(db, storefront)

    assert facts_for(db, conversation) is None


def test_an_unpaid_order_is_not_yet_a_customer(db, checkout, storefront):
    """Before the money lands there is no workspace for any of this to be true of."""
    conversation = web_thread(db, storefront)
    make_order(checkout, storefront, conversation=conversation)

    assert facts_for(db, conversation) is None


def test_a_paid_buyer_in_their_own_purchase_thread_is_a_customer(
    db, checkout, transport, storefront
):
    conversation = telegram_thread(db, storefront)
    bought(db, checkout, transport, storefront, conversation)

    setup = facts_for(db, conversation)

    assert setup is not None
    assert setup.is_customer is True
    assert setup.workspace_ready is True
    assert setup.has_widget_token is True


def test_a_customers_own_end_customer_is_not_treated_as_the_customer(
    db, checkout, transport, storefront
):
    """The cross-tenant test, and the reason the link is an order and not an org.

    A conversation inside the provisioned workspace is somebody talking to the
    customer's agent — a shopper, not the shop owner. If this ever returns facts,
    a shopper asking "it's not working" about a delivery gets told which page to
    republish, signed by the shop's own agent.
    """
    purchase = telegram_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, purchase)

    profile = (
        db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == order.id).one()
    )
    shopper = Conversation(
        organization_id=profile.organization_id,
        workspace_profile_id=profile.id,
        public_token="tok-a-shopper",
    )
    db.add(shopper)
    db.commit()

    assert facts_for(db, shopper) is None


def test_another_buyers_thread_does_not_see_this_buyers_workspace(
    db, checkout, transport, storefront
):
    """Two buyers, two threads, and no leakage between them."""
    first = telegram_thread(db, storefront, chat_id="1111")
    second = telegram_thread(db, storefront, chat_id="2222")
    bought(db, checkout, transport, storefront, first)

    assert facts_for(db, first) is not None
    assert facts_for(db, second) is None


def test_a_paid_order_with_nothing_provisioned_is_still_a_customer(
    db, checkout, transport, storefront
):
    """Paid, and nothing built. They are owed something, so they are a customer.

    ``workspace_ready`` False is what makes the engine say the build has not
    finished rather than send them looking for a snippet that was never issued.
    """
    conversation = web_thread(db, storefront)
    order = make_order(checkout, storefront, conversation=conversation)
    pay(checkout, transport, order)

    setup = facts_for(db, conversation)

    assert setup is not None
    assert setup.is_customer is True
    assert setup.workspace_ready is False


# ---------------------------------------------------------------------------
# What the facts say
# ---------------------------------------------------------------------------


def test_a_snippet_that_has_never_run_reads_as_never_seen(
    db, checkout, transport, storefront
):
    conversation = web_thread(db, storefront)
    bought(db, checkout, transport, storefront, conversation)

    setup = facts_for(db, conversation)

    assert setup.widget_last_seen is None
    assert setup.widget_never_seen is True


def test_a_snippet_that_has_run_is_read_back_from_the_stamp(
    db, checkout, transport, storefront
):
    """The column, the route that writes it and the fact that reads it, joined up."""
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    profile = (
        db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == order.id).one()
    )
    profile.widget_last_seen_at = datetime.now(UTC) - timedelta(minutes=2)
    db.commit()

    setup = facts_for(db, conversation)

    assert setup.widget_never_seen is False
    assert setup.widget_seen_recently is True


def test_the_widget_route_is_what_stamps_it(db, client, checkout, transport, storefront):
    """End to end: a page carrying the snippet asks for its config, and we know.

    This is the only observation we get for free, so it is worth asserting that
    the observation actually happens rather than only that the column exists.
    """
    conversation = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, conversation)

    profile = (
        db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == order.id).one()
    )
    assert profile.widget_last_seen_at is None

    response = client.get(f"/api/v1/widget/{profile.widget_token}/config")

    assert response.status_code == 200

    db.refresh(profile)
    assert profile.widget_last_seen_at is not None
    assert facts_for(db, conversation).widget_seen_recently is True


def test_the_channels_bought_come_from_the_quote_that_was_paid(
    db, checkout, transport, storefront
):
    """What they were charged for, not what we hope they wanted.

    ``BOTH_PRODUCTS_BUILD`` includes WhatsApp, which is priced at ₦8,000 and is
    not provisioned by anything. That gap is the point of the next test.
    """
    conversation = web_thread(db, storefront)
    bought(
        db, checkout, transport, storefront, conversation, build=BOTH_PRODUCTS_BUILD
    )

    setup = facts_for(db, conversation)

    assert CHANNEL_WHATSAPP in setup.bought_channels
    assert CHANNEL_WEB in setup.bought_channels


def test_a_paid_channel_that_nothing_provisions_shows_up_as_owed(
    db, checkout, transport, storefront
):
    """The real gap, asserted against live behaviour rather than a note in a file.

    Provisioning issues a widget token and nothing else. There is no per-customer
    Telegram bot and no WhatsApp number, so a customer who paid for either has
    bought something that does not exist yet — and this is the test that says so
    out loud instead of letting it stay a comment.
    """
    conversation = telegram_thread(db, storefront)
    bought(
        db,
        checkout,
        transport,
        storefront,
        conversation,
        build=Requirement(
            product_type=PRODUCT_SALES_AGENT,
            channels=(CHANNEL_WEB, CHANNEL_TELEGRAM),
            monthly_conversations=2_000,
        ),
    )

    setup = facts_for(db, conversation)

    assert CHANNEL_TELEGRAM in setup.bought_channels
    assert CHANNEL_TELEGRAM not in setup.live_channels
    assert setup.channels_owed == (CHANNEL_TELEGRAM,)


def test_a_web_only_purchase_owes_nothing(db, checkout, transport, storefront):
    """The common case, and it must not manufacture a debt.

    A false "you paid for something we didn't build" would escalate a working
    customer's ordinary question and tell them we owe them something we don't.
    """
    conversation = web_thread(db, storefront)
    bought(db, checkout, transport, storefront, conversation, build=SALES_BUILD)

    assert facts_for(db, conversation).channels_owed == ()


def test_two_agents_are_only_ready_when_both_are(
    db, checkout, transport, storefront
):
    """A half-provisioned workspace is mid-build, not finished.

    Telling a customer the build is done while one of their two agents is still
    pending sends them hunting for a fault that is ours.
    """
    conversation = web_thread(db, storefront)
    order = bought(
        db, checkout, transport, storefront, conversation, build=BOTH_PRODUCTS_BUILD
    )

    profiles = (
        db.query(WorkspaceProfile)
        .filter(WorkspaceProfile.order_id == order.id)
        .order_by(WorkspaceProfile.id)
        .all()
    )
    assert len(profiles) == 2
    assert facts_for(db, conversation).workspace_ready is True

    profiles[1].status = PROVISION_PENDING
    db.commit()

    assert facts_for(db, conversation).workspace_ready is False


def test_one_agent_is_named_and_two_are_not(db, checkout, transport, storefront):
    """"Ada answers out of your material" is only accurate if Ada is the only one."""
    single = web_thread(db, storefront)
    bought(db, checkout, transport, storefront, single, build=SALES_BUILD)

    assert facts_for(db, single).agent_name != ""

    both = telegram_thread(db, storefront, chat_id="3333")
    bought(db, checkout, transport, storefront, both, build=BOTH_PRODUCTS_BUILD)

    assert facts_for(db, both).agent_name == ""


def test_conversations_handled_counts_only_threads_the_agent_answered(
    db, checkout, transport, storefront
):
    """Evidence, not row count.

    The number is quoted back to a customer as proof their agent works. A thread
    that was opened and abandoned proves nothing, and counting it would make the
    proof false.
    """
    purchase = web_thread(db, storefront)
    order = bought(db, checkout, transport, storefront, purchase)

    profile = (
        db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == order.id).one()
    )
    service = ConversationService(db)

    assert facts_for(db, purchase).conversations_handled == 0

    opened_and_abandoned = Conversation(
        organization_id=profile.organization_id,
        workspace_profile_id=profile.id,
        public_token="tok-abandoned",
    )
    db.add(opened_and_abandoned)
    db.commit()

    assert facts_for(db, purchase).conversations_handled == 0

    answered = service.start(profile.organization_id, profile.id)
    service.handle_visitor_message(answered, "hello, do you sell trousers?")

    assert facts_for(db, purchase).conversations_handled == 1


# ---------------------------------------------------------------------------
# Through the service, on the channel the customer is actually on
# ---------------------------------------------------------------------------


def test_a_customer_reporting_a_fault_in_their_purchase_thread_is_diagnosed(
    db, checkout, transport, storefront
):
    """The whole path, from a real Telegram thread with a real paid order.

    Everything before this test asserts a piece. This asserts that the pieces are
    connected — which is the failure mode the delivery bug was: every part worked
    and the buyer was still told nothing.
    """
    conversation = telegram_thread(db, storefront)
    bought(db, checkout, transport, storefront, conversation)

    reply = ConversationService(db).handle_visitor_message(
        conversation, "the chat is not showing up on my site"
    )

    assert RULE_DIAGNOSED in (reply.reasoning_json or "")
    assert "never" in reply.body.lower()
    assert "Which of these do you need?" not in reply.body


def test_a_customer_asking_to_buy_more_is_still_sold_to(
    db, checkout, transport, storefront
):
    """A customer is still a buyer, through the real service.

    Every conversation past the support gate has a paid order behind it. If the
    gate swallowed purchase intent, adding support would have closed the upsell
    channel to fix the complaint channel.
    """
    conversation = telegram_thread(db, storefront, chat_id="4444")
    bought(db, checkout, transport, storefront, conversation)

    reply = ConversationService(db).handle_visitor_message(
        conversation, "what would a support agent cost as well?"
    )

    assert RULE_SUPPORT_ESCALATED not in (reply.reasoning_json or "")


def test_a_customer_owed_a_channel_is_told_the_truth_about_it(
    db, checkout, transport, storefront
):
    """The one escalation the facts justify, end to end.

    Escalated, because nothing here can switch on a Telegram bot that provisioning
    does not create. Owned rather than deflected, because the customer paid for it.
    """
    conversation = telegram_thread(db, storefront, chat_id="5555")
    bought(
        db,
        checkout,
        transport,
        storefront,
        conversation,
        build=Requirement(
            product_type=PRODUCT_SALES_AGENT,
            channels=(CHANNEL_WEB, CHANNEL_TELEGRAM),
            monthly_conversations=2_000,
        ),
    )

    reply = ConversationService(db).handle_visitor_message(
        conversation, "where is my telegram bot?"
    )

    assert RULE_SUPPORT_ESCALATED in (reply.reasoning_json or "")
    assert "on us" in reply.body
