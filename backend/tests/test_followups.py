"""Post-sale follow-up tests.

The retention loop. Less dangerous than the money path, but it is the part of
the system that writes to customers unprompted, so the cases that matter are
the ones about restraint: not sending twice, not sending a note whose premise
stopped being true, not claiming to have sent something that never left.

The sender is injected, so nothing here touches a network or needs an email
account.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import settings
from app.followups.rules import RULES, RULES_BY_CODE, FollowUpContext
from app.followups.service import (
    Delivery,
    FollowUpSendError,
    FollowUpService,
    UnconfiguredSender,
)
from app.models.conversation import Conversation
from app.models.follow_up import (
    STATUS_CANCELLED,
    STATUS_SCHEDULED,
    STATUS_SENT,
    FollowUp,
)
from app.models.order import Order
from app.models.organization import Organization
from app.payments.checkout import CheckoutService
from app.payments.paystack import PaystackClient
from app.payments.provisioning import ProvisioningService
from app.pricing.complexity import (
    CHANNEL_WEB,
    PRODUCT_SALES_AGENT,
    Requirement,
    price,
)
from app.pricing.quotes import QuoteService, plan_code_for

# What a follow-up is written about: a build somebody bought. The storefront
# sells no tiers, so there is no default plan to borrow a name and a price from
# — both come from the engine, which is where a real order's did.
SOLD_BUILD = Requirement(
    product_type=PRODUCT_SALES_AGENT,
    channels=(CHANNEL_WEB,),
    monthly_conversations=2_000,
)

SOLD = price(SOLD_BUILD)

TEST_SECRET = "sk_test_pretend_key_for_tests"


class RecordingSender:
    """Captures what would have gone out."""

    def __init__(self):
        self.sent: list[Delivery] = []

    def send(self, delivery: Delivery) -> None:
        self.sent.append(delivery)


class ExplodingSender:
    """A provider having a bad day."""

    def send(self, delivery: Delivery) -> None:
        raise FollowUpSendError("The provider returned 502.")


class FakeTransport:
    def request(self, method, url, *, headers, json_body=None):
        if "/transaction/initialize" in url:
            reference = (json_body or {}).get("reference", "ref_unknown")
            return 200, {
                "status": True,
                "data": {
                    "authorization_url": f"https://checkout.paystack.com/{reference}",
                    "access_code": "acc_" + reference,
                    "reference": reference,
                },
            }

        if "/transaction/verify/" in url:
            reference = url.rsplit("/", 1)[-1]
            return 200, {
                "status": True,
                "data": {
                    "reference": reference,
                    "status": "success",
                    "amount": SOLD.total_minor,
                    "currency": SOLD.currency,
                },
            }

        return 404, {"status": False, "message": "unexpected"}


@pytest.fixture
def storefront(db) -> Organization:
    org = Organization(name="NekoSalesAI Demo", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def paid_order(db, storefront) -> Order:
    client = PaystackClient(secret_key=TEST_SECRET, transport=FakeTransport())
    checkout = CheckoutService(db, client=client)

    order = checkout.create_order(
        organization_id=storefront.id,
        quote_reference=QuoteService(db).issue(SOLD_BUILD).reference,
        buyer_email="buyer@example.com",
        buyer_name="Ada Buyer",
        buyer_company="Buyer Co",
    )

    return checkout.confirm_by_reference(order.paystack_reference)


@pytest.fixture
def workspace(db, paid_order):
    return ProvisioningService(db).provision(paid_order).profile


@pytest.fixture
def service(db) -> FollowUpService:
    return FollowUpService(db, sender=RecordingSender())


# ---------- scheduling ----------


def test_paying_puts_the_whole_calendar_on_the_books(service, workspace, paid_order):
    created = service.schedule_for(workspace, paid_order)

    assert len(created) == len(RULES)
    assert {f.rule_code for f in created} == {r.code for r in RULES}
    assert all(f.status == STATUS_SCHEDULED for f in created)


def test_each_follow_up_is_dated_from_when_the_workspace_went_live(
    service, workspace, paid_order
):
    created = service.schedule_for(workspace, paid_order)

    for follow_up in created:
        rule = RULES_BY_CODE[follow_up.rule_code]
        expected = workspace.ready_at + timedelta(days=rule.day_offset)
        assert follow_up.due_at == expected


def test_follow_ups_are_filed_against_the_seller_not_the_buyer(
    service, workspace, paid_order, storefront
):
    """The queue has to land on the desk of whoever made the sale.

    Provisioning creates a second organization for the buyer. Filing the
    follow-ups there would put them in a tenant the seller cannot read.
    """
    created = service.schedule_for(workspace, paid_order)

    assert workspace.organization_id != storefront.id
    assert all(f.organization_id == storefront.id for f in created)


def test_scheduling_twice_does_not_duplicate_the_calendar(
    service, workspace, paid_order, db
):
    """The status page polls every 1.5s and each poll re-runs provisioning."""
    service.schedule_for(workspace, paid_order)
    second = service.schedule_for(workspace, paid_order)

    assert second == []
    assert db.query(FollowUp).count() == len(RULES)


def test_an_unprovisioned_workspace_gets_no_calendar(service, db, paid_order):
    from app.models.workspace_profile import PROVISION_PENDING, WorkspaceProfile

    profile = WorkspaceProfile(
        organization_id=paid_order.organization_id,
        order_id=paid_order.id,
        plan_code=paid_order.plan_code,
        status=PROVISION_PENDING,
        agent_name="Ada",
        company_name="Half Built",
        greeting="hello",
    )
    db.add(profile)
    db.commit()

    assert service.schedule_for(profile, paid_order) == []


# ---------- the due queue ----------


def test_only_the_day_zero_note_is_due_immediately(service, workspace, paid_order):
    service.schedule_for(workspace, paid_order)

    due = service.due(paid_order.organization_id)

    assert [f.rule_code for f in due] == ["day_0_workspace_live"]


def test_later_rules_come_due_on_their_day(service, workspace, paid_order):
    service.schedule_for(workspace, paid_order)

    later = workspace.ready_at + timedelta(days=7, minutes=1)
    due = service.due(paid_order.organization_id, now=later)

    assert [f.day_offset for f in due] == [0, 1, 3, 7]


def test_the_due_queue_is_scoped_to_one_organization(
    service, workspace, paid_order, db
):
    service.schedule_for(workspace, paid_order)

    other = Organization(name="Someone Else", slug="someone-else")
    db.add(other)
    db.commit()

    assert service.due(other.id) == []


# ---------- sending ----------


def test_sending_delivers_to_the_buyer_and_records_it(db, workspace, paid_order):
    sender = RecordingSender()
    service = FollowUpService(db, sender=sender)
    service.schedule_for(workspace, paid_order)

    follow_up = service.due(paid_order.organization_id)[0]
    sent = service.send(follow_up)

    assert sent.status == STATUS_SENT
    assert sent.sent_at is not None
    assert len(sender.sent) == 1
    assert sender.sent[0].to_email == "buyer@example.com"


def test_the_same_follow_up_cannot_be_sent_twice(db, workspace, paid_order):
    sender = RecordingSender()
    service = FollowUpService(db, sender=sender)
    service.schedule_for(workspace, paid_order)

    follow_up = service.due(paid_order.organization_id)[0]
    service.send(follow_up)

    with pytest.raises(FollowUpSendError):
        service.send(follow_up)

    assert len(sender.sent) == 1


def test_a_failed_send_leaves_the_follow_up_open(db, workspace, paid_order):
    """A provider outage must not silently consume the message."""
    service = FollowUpService(db, sender=ExplodingSender())
    service.schedule_for(workspace, paid_order)

    follow_up = service.due(paid_order.organization_id)[0]

    with pytest.raises(FollowUpSendError):
        service.send(follow_up)

    db.refresh(follow_up)
    assert follow_up.status == STATUS_SCHEDULED
    assert follow_up.sent_at is None


def test_with_no_sender_configured_nothing_is_marked_sent(db, workspace, paid_order):
    """The default must refuse rather than pretend."""
    service = FollowUpService(db)  # UnconfiguredSender
    service.schedule_for(workspace, paid_order)

    follow_up = service.due(paid_order.organization_id)[0]

    with pytest.raises(FollowUpSendError):
        service.send(follow_up)

    db.refresh(follow_up)
    assert follow_up.status == STATUS_SCHEDULED


def test_the_unconfigured_sender_says_what_to_do_instead():
    with pytest.raises(FollowUpSendError) as exc:
        UnconfiguredSender().send(
            Delivery(to_email="a@b.com", subject="s", body="b")
        )

    assert "send it yourself" in str(exc.value)


def test_a_human_can_record_a_send_they_made_themselves(db, workspace, paid_order):
    service = FollowUpService(db)
    service.schedule_for(workspace, paid_order)

    follow_up = service.due(paid_order.organization_id)[0]
    marked = service.mark_sent_manually(follow_up)

    assert marked.status == STATUS_SENT
    assert marked.sent_at is not None


# ---------- restraint: the rules that withdraw themselves ----------


def test_the_day_one_nudge_is_withdrawn_once_traffic_arrives(
    db, workspace, paid_order
):
    """The point of re-checking at send time.

    The calendar is written on day zero and cannot know the customer will go
    live on day one. Sending "nothing has reached you yet" to somebody whose
    rep is already working is the exact failure this guards.
    """
    sender = RecordingSender()
    service = FollowUpService(db, sender=sender)
    service.schedule_for(workspace, paid_order)

    db.add(
        Conversation(
            organization_id=workspace.organization_id,
            public_token="tok_traffic_arrived",
            stage="discovery",
        )
    )
    db.commit()

    day_one = next(
        f
        for f in service.list(paid_order.organization_id)
        if f.rule_code == "day_1_install_widget"
    )
    result = service.send(day_one)

    assert result.status == STATUS_CANCELLED
    assert "Overtaken by events" in result.cancelled_reason
    assert sender.sent == []


def test_the_first_week_review_is_withdrawn_when_there_was_no_first_week(
    db, workspace, paid_order
):
    """Its own mirror image: do not send a review of nothing."""
    sender = RecordingSender()
    service = FollowUpService(db, sender=sender)
    service.schedule_for(workspace, paid_order)

    day_seven = next(
        f
        for f in service.list(paid_order.organization_id)
        if f.rule_code == "day_7_first_week_review"
    )
    result = service.send(day_seven)

    assert result.status == STATUS_CANCELLED
    assert sender.sent == []


def test_a_follow_up_whose_rule_was_deleted_is_never_sent(
    db, workspace, paid_order
):
    sender = RecordingSender()
    service = FollowUpService(db, sender=sender)
    service.schedule_for(workspace, paid_order)

    orphan = service.due(paid_order.organization_id)[0]
    orphan.rule_code = "rule_that_no_longer_exists"
    db.commit()

    result = service.send(orphan)

    assert result.status == STATUS_CANCELLED
    assert sender.sent == []


def test_cancelling_records_the_reason(db, workspace, paid_order, service):
    service.schedule_for(workspace, paid_order)
    follow_up = service.due(paid_order.organization_id)[0]

    cancelled = service.cancel(follow_up, "Customer asked us to stop emailing.")

    assert cancelled.status == STATUS_CANCELLED
    assert cancelled.cancelled_reason == "Customer asked us to stop emailing."


# ---------- the message itself ----------


def test_the_body_is_rendered_from_the_customers_own_facts(
    service, workspace, paid_order
):
    service.schedule_for(workspace, paid_order)
    day_zero = service.due(paid_order.organization_id)[0]

    assert "Buyer Co" in day_zero.subject
    assert "Ada" in day_zero.body                       # buyer's first name
    assert SOLD.product_name in day_zero.body
    assert workspace.api_key_prefix in day_zero.body


def test_the_price_quoted_is_the_price_actually_paid(
    service, workspace, paid_order
):
    """The one number a follow-up must never get wrong."""
    from app.catalog import format_money

    service.schedule_for(workspace, paid_order)
    day_zero = service.due(paid_order.organization_id)[0]

    assert (
        format_money(paid_order.amount_minor, paid_order.currency)
        in day_zero.body
    )


def test_the_body_is_re_rendered_against_todays_facts_at_send_time(
    db, workspace, paid_order
):
    """A month-old draft would quote a month-old conversation count."""
    sender = RecordingSender()
    service = FollowUpService(db, sender=sender)
    service.schedule_for(workspace, paid_order)

    for index in range(3):
        db.add(
            Conversation(
                organization_id=workspace.organization_id,
                public_token=f"tok_later_{index}",
                stage="discovery",
            )
        )
    db.commit()

    day_seven = next(
        f
        for f in service.list(paid_order.organization_id)
        if f.rule_code == "day_7_first_week_review"
    )
    sent = service.send(day_seven)

    assert "3 conversation(s)" in sent.body
    assert "3 conversation(s)" in sender.sent[0].body


def test_every_follow_up_carries_its_reasoning(service, workspace, paid_order):
    from app.sales.reasoning import Reasoning

    created = service.schedule_for(workspace, paid_order)

    for follow_up in created:
        reasoning = Reasoning.from_json(follow_up.reasoning_json)
        assert reasoning is not None
        assert reasoning.rule == follow_up.rule_code
        assert reasoning.signals
        assert reasoning.grounded_in == [f"plan:{paid_order.plan_code}"]


def test_no_follow_up_claims_a_confidence_score(service, workspace, paid_order):
    """The standing rule, asserted rather than assumed."""
    created = service.schedule_for(workspace, paid_order)

    for follow_up in created:
        blob = (follow_up.reasoning_json or "").lower()
        assert "confidence" not in blob
        assert "%" not in follow_up.body


def test_a_buyer_without_a_name_is_addressed_by_company(db, storefront):
    context = FollowUpContext(
        company_name="Nameless Ltd",
        buyer_name=None,
        plan_code=plan_code_for("qt_pretend_reference"),
        plan_name=SOLD.product_name,
        amount_minor=SOLD.total_minor,
        currency=SOLD.currency,
        api_key_prefix="nsk_live_ab",
        conversation_count=0,
        support_email="support@example.com",
        dashboard_url="http://example.com/desk",
    )

    assert context.first_name == "Nameless Ltd"


def test_every_rule_renders_without_a_name_or_an_api_key():
    """Provisioning can leave either absent. Neither may crash a send."""
    context = FollowUpContext(
        company_name="Sparse Co",
        buyer_name=None,
        plan_code=plan_code_for("qt_pretend_reference"),
        plan_name=SOLD.product_name,
        amount_minor=SOLD.total_minor,
        currency=SOLD.currency,
        api_key_prefix=None,
        conversation_count=0,
        support_email="support@example.com",
        dashboard_url="http://example.com/desk",
    )

    for rule in RULES:
        subject, body, reasoning = rule.render(context)
        assert subject and body
        assert "None" not in body
        assert reasoning.rule == rule.code


# ---------- what the emails actually say ----------
#
# The two defects here came out of a real purchase. The delivery message was
# fixed for both and the emails were not, so the same two sentences went on
# reaching customers from a different file. These tests are the reason the next
# rewrite of either one cannot leave the other behind.


def email_context(**overrides) -> FollowUpContext:
    """A working, installed customer — then whatever the test changes."""
    base = dict(
        company_name="Buyer Co",
        buyer_name="Ada Buyer",
        plan_code=plan_code_for("qt_pretend_reference"),
        plan_name=SOLD.product_name,
        amount_minor=SOLD.total_minor,
        currency=SOLD.currency,
        api_key_prefix="nks_live_abcd",
        conversation_count=12,
        support_email="support@example.com",
        dashboard_url="http://example.com/desk",
        agent_name="Ada",
        widget_token="wtok-abcdef123456",
        widget_last_seen=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    base.update(overrides)

    return FollowUpContext(**base)


def rendered(code: str, **overrides) -> str:
    return RULES_BY_CODE[code].render(email_context(**overrides))[1]


def prose(code: str, **overrides) -> str:
    """The body with its line wrapping collapsed.

    The copy is hard-wrapped for email, so "The install is not\\nthe problem"
    contains the sentence and does not contain the string. Asserting on the
    wrapped text would make every assertion here depend on where a line happened
    to break, and a reflowed paragraph would fail a test about its meaning.
    """
    return " ".join(rendered(code, **overrides).split())


def test_the_welcome_email_gives_real_install_steps_not_an_instruction_to_paste():
    """The sentence a paying customer was actually sent.

    "Paste your widget snippet into your site" assumes the buyer already knows
    what a snippet is, where theirs is, and where in their site it goes. It is
    the one line in the email that had to be a page.
    """
    body = prose("day_0_workspace_live")

    assert "Paste your widget snippet into your site" not in body
    # The snippet itself, their own token in it, and where it goes on the
    # platform they are most likely to be on.
    assert "wtok-abcdef123456" in body
    assert "</body>" in body
    assert "WordPress" in body
    assert "theme.liquid" in body
    # And what to do when it does not appear, rather than "reply and we'll look".
    assert "Ctrl+Shift+R" in body


def test_no_email_closes_by_defaulting_to_a_person():
    """The other half of the same fix, across the whole calendar.

    Reflexive escalation is not a tone problem. An email that answers a question
    and then says "reply and it reaches a person" has told the customer the
    answer above it was not the real one.
    """
    offenders = [
        rule.code
        for rule in RULES
        if "It reaches a person" in " ".join(rule.render(email_context())[1].split())
    ]

    assert offenders == []


def test_a_customer_whose_snippet_is_running_is_not_told_to_install_it():
    """The complaint a support email earns when it does not read the facts.

    Every install email used to say the same thing to everybody, including the
    customers whose snippet was demonstrably loading from their own site. Being
    told to do the thing you have already done is why these get filtered.
    """
    for code in ("day_1_install_widget", "day_3_no_conversations"):
        body = prose(code, conversation_count=0)

        assert "has never loaded" not in body, code
        assert "has not gone onto the site" not in body, code
        assert "the install is fine" in body or "install is not the problem" in body


def test_the_install_emails_say_something_different_to_each_kind_of_workspace():
    """Three states, three messages, asserted as a difference.

    Never loaded, loading now, and loaded-then-stopped are three different
    problems with three different fixes. Asserted against each other rather than
    against fixed strings so the property survives the copy being rewritten.
    """
    for code in ("day_1_install_widget", "day_3_no_conversations"):
        never = rendered(code, conversation_count=0, widget_last_seen=None)
        now = rendered(code, conversation_count=0)
        stopped = rendered(
            code,
            conversation_count=0,
            widget_last_seen=datetime.now(timezone.utc) - timedelta(days=9),
        )

        assert len({never, now, stopped}) == 3, code


def test_a_workspace_nobody_ever_installed_is_told_so_at_two_months():
    """Blunt on purpose, and it offers the way out as well as the way forward."""
    body = prose("day_60_never_used", conversation_count=0, widget_last_seen=None)

    assert "never loaded from your site" in body
    assert "a person will sort out your account" in body


def test_no_email_claims_a_second_charge():
    """Nothing in the system bills again, so nothing may say it did.

    ``subscription_plan`` is a label on an organization. There is no recurring
    charge, no renewal date and no second Paystack transaction, so a day-60 email
    saying "you have paid twice" would be inventing a fact about somebody's money
    — the single worst kind to get wrong.
    """
    claims = ("paid twice", "charged again", "renews", "renewal date", "next payment")
    offenders = [
        (rule.code, claim)
        for rule in RULES
        for used in (email_context(conversation_count=0), email_context())
        for claim in claims
        if claim in " ".join(rule.render(used)[1].split()).lower()
    ]

    assert offenders == []


# ---------- the calendar ----------


def test_the_calendar_runs_to_six_months():
    """Extended past day 30, and every offset counted from day 0.

    ``due_at`` is ``ready_at + day_offset``, so an offset is days since the
    workspace went live and not days since the previous email. A rule added
    relative to the one before it would drift the whole tail.
    """
    assert [rule.day_offset for rule in RULES] == [
        0, 1, 3, 7, 14, 30, 60, 60, 90, 180
    ]


def test_the_two_day_sixty_rules_are_mutually_exclusive():
    """Same offset, opposite conditions, so exactly one of them ever sends.

    Both are scheduled — conditions are optimistic at schedule time — and
    ``send`` cancels the one whose condition no longer holds. If both could
    apply, a customer would get two emails on the same morning contradicting
    each other about whether their rep was working.
    """
    dormant = RULES_BY_CODE["day_60_never_used"]
    working = RULES_BY_CODE["day_60_spot_check"]

    assert dormant.day_offset == working.day_offset

    for count in (0, 1, 40):
        context = email_context(conversation_count=count)

        assert dormant.applies(context) != working.applies(context), count


def test_the_long_tail_only_goes_to_workspaces_that_are_being_used():
    """Nothing past day 60 is sent to a workspace that has never been used.

    A dormant customer has been told the truth once, at day 60, and offered a way
    out. Sending them a quarterly catalog review after that is nagging somebody
    about maintaining a thing they never switched on.
    """
    unused = email_context(conversation_count=0, widget_last_seen=None)

    for code in ("day_90_catalog_review", "day_180_half_year"):
        assert RULES_BY_CODE[code].applies(unused) is False


def test_the_quarterly_email_names_the_limitation_rather_than_hiding_it():
    """A stale catalog is quoted confidently, and nothing flags it.

    That is a real property of a deterministic engine reading published entries,
    and the customer is the only one who can fix it — so it has to be said.
    """
    body = prose("day_90_catalog_review")

    assert "stale" in body
    assert "nothing in the system will flag it" in body


def test_every_follow_up_survives_being_pushed_to_a_chat_channel():
    """Follow-ups are not email-only, and chat platforms reject long messages.

    A customer can tick Telegram or WhatsApp, and ``FollowUpDispatcher`` pushes
    ``subject + body`` to them. Both cap a message at 4,096 characters and reject
    anything longer with a 400, which the dispatcher records as a failed channel —
    so an email that grew past the cap would stop arriving on that channel and the
    only trace would be a log line.

    The day-0 email is over the cap now that it carries the full install steps, so
    this is not hypothetical. It is safe because the clients split first; this
    asserts the split holds and, more importantly, that it never cuts through the
    snippet the customer has to copy.
    """
    from app.messaging.clients import MESSAGE_LIMIT, split_for_delivery

    for rule in RULES:
        for context in (email_context(), email_context(conversation_count=0)):
            if not rule.applies(context):
                continue

            subject, body, _ = rule.render(context)
            pieces = split_for_delivery(f"{subject}\n\n{body}")

            assert all(len(piece) <= MESSAGE_LIMIT for piece in pieces), rule.code

            # The snippet is the one thing in here that is useless in halves.
            if context.widget_token and context.widget_token in body:
                intact = [p for p in pieces if context.widget_token in p]
                assert len(intact) == 1, rule.code
                assert "<script" in intact[0] and "</script>" in intact[0], rule.code


# ---------- the desk API ----------


@pytest.fixture
def desk(client, db, storefront):
    """An authenticated staff user in the selling organization."""
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        email="desk@example.com",
        full_name="Desk User",
        password_hash=hash_password("desk-password-1"),
        organization_id=storefront.id,
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.commit()

    token = client.post(
        "/api/v1/auth/login",
        json={"email": "desk@example.com", "password": "desk-password-1"},
    ).json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


def test_the_follow_up_queue_requires_authentication(client):
    assert client.get("/api/v1/sales-desk/follow-ups").status_code in (401, 403)


def test_the_desk_lists_the_queue_with_recipients(
    client, desk, service, workspace, paid_order
):
    service.schedule_for(workspace, paid_order)

    response = client.get("/api/v1/sales-desk/follow-ups", headers=desk)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(RULES)
    assert body[0]["recipient"] == "buyer@example.com"
    assert body[0]["company_name"] == "Buyer Co"
    assert body[0]["reasoning"]["rule"] == body[0]["rule_code"]


def test_the_desk_can_ask_for_only_what_is_due(
    client, desk, service, workspace, paid_order
):
    service.schedule_for(workspace, paid_order)

    response = client.get(
        "/api/v1/sales-desk/follow-ups?due_only=true", headers=desk
    )

    assert [f["rule_code"] for f in response.json()] == ["day_0_workspace_live"]


def test_sending_without_a_configured_sender_returns_a_conflict_not_a_lie(
    client, desk, service, workspace, paid_order
):
    service.schedule_for(workspace, paid_order)
    follow_up = service.due(paid_order.organization_id)[0]

    response = client.post(
        f"/api/v1/sales-desk/follow-ups/{follow_up.id}/send", headers=desk
    )

    assert response.status_code == 409
    assert "send it yourself" in response.json()["detail"]


def test_the_desk_can_mark_a_follow_up_sent_by_hand(
    client, desk, service, workspace, paid_order
):
    service.schedule_for(workspace, paid_order)
    follow_up = service.due(paid_order.organization_id)[0]

    response = client.post(
        f"/api/v1/sales-desk/follow-ups/{follow_up.id}/mark-sent", headers=desk
    )

    assert response.status_code == 200
    assert response.json()["status"] == STATUS_SENT


def test_cancelling_through_the_desk_requires_a_reason(
    client, desk, service, workspace, paid_order
):
    service.schedule_for(workspace, paid_order)
    follow_up = service.due(paid_order.organization_id)[0]

    empty = client.post(
        f"/api/v1/sales-desk/follow-ups/{follow_up.id}/cancel",
        json={"reason": ""},
        headers=desk,
    )
    assert empty.status_code == 422

    ok = client.post(
        f"/api/v1/sales-desk/follow-ups/{follow_up.id}/cancel",
        json={"reason": "They asked us to stop."},
        headers=desk,
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == STATUS_CANCELLED


def test_one_organization_cannot_touch_anothers_follow_ups(
    client, desk, db, service, workspace, paid_order
):
    """The tenant boundary, asserted at the route rather than the service."""
    from app.core.security import hash_password
    from app.models.user import User

    service.schedule_for(workspace, paid_order)
    target = service.due(paid_order.organization_id)[0]

    intruder_org = Organization(name="Intruder Ltd", slug="intruder-ltd")
    db.add(intruder_org)
    db.commit()

    db.add(
        User(
            email="intruder@example.com",
            full_name="Intruder",
            password_hash=hash_password("intruder-password-1"),
            organization_id=intruder_org.id,
            is_admin=True,
            is_active=True,
        )
    )
    db.commit()

    token = client.post(
        "/api/v1/auth/login",
        json={"email": "intruder@example.com", "password": "intruder-password-1"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/sales-desk/follow-ups", headers=headers).json() == []

    for action in ("send", "mark-sent"):
        response = client.post(
            f"/api/v1/sales-desk/follow-ups/{target.id}/{action}", headers=headers
        )
        assert response.status_code == 404

    cancelled = client.post(
        f"/api/v1/sales-desk/follow-ups/{target.id}/cancel",
        json={"reason": "not mine to cancel"},
        headers=headers,
    )
    assert cancelled.status_code == 404

    db.refresh(target)
    assert target.status == STATUS_SCHEDULED


def test_the_desk_summary_counts_what_is_actually_due(
    client, desk, service, workspace, paid_order
):
    service.schedule_for(workspace, paid_order)

    summary = client.get("/api/v1/sales-desk/summary", headers=desk).json()

    assert summary["follow_ups_due"] == 1
