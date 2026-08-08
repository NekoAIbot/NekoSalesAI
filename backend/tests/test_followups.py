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

from app.catalog import PLANS
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

DEFAULT_PLAN = next(p for p in PLANS if p.is_default)

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
                    "amount": DEFAULT_PLAN.amount_minor,
                    "currency": DEFAULT_PLAN.currency,
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
        plan_code=DEFAULT_PLAN.code,
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
    assert DEFAULT_PLAN.name in day_zero.body
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
        plan_code=DEFAULT_PLAN.code,
        plan_name=DEFAULT_PLAN.name,
        amount_minor=DEFAULT_PLAN.amount_minor,
        currency=DEFAULT_PLAN.currency,
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
        plan_code=DEFAULT_PLAN.code,
        plan_name=DEFAULT_PLAN.name,
        amount_minor=DEFAULT_PLAN.amount_minor,
        currency=DEFAULT_PLAN.currency,
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
