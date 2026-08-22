"""Email, and the delivery of follow-ups through it.

Before this release the project could not send a message. Receipts were promised
on the landing page and never sent, the one-time admin password was shown on a
screen and stored nowhere, and the six scheduled follow-ups were only ever
displayed in the desk. These tests cover the parts where a mistake is expensive:
a credential that never arrives and cannot be reissued, and a follow-up marked
sent that nobody received.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.followups.runner import due_across_organizations, run_due
from app.followups.sender import MailSender
from app.followups.service import Delivery, FollowUpSendError, FollowUpService
from app.mail import (
    MemoryMailTransport,
    Message,
    build_transport,
    credentials,
    receipt,
    set_transport,
)
from app.models.follow_up import STATUS_SCHEDULED, STATUS_SENT
from app.models.order import ORDER_PAID, Order
from app.models.organization import Organization
from app.models.workspace_profile import PROVISION_READY, WorkspaceProfile


@pytest.fixture
def outbox():
    """A transport that collects instead of sending, installed for one test."""
    transport = MemoryMailTransport()
    set_transport(transport)

    yield transport

    # Reset, or the next test inherits this one's outbox.
    set_transport(None)


# ---------- composing ----------


def test_a_receipt_states_the_amount_that_was_charged(outbox):
    """The figure is passed in, so the receipt cannot disagree with the order."""
    message = receipt(
        to="buyer@example.com",
        company_name="Bright Dental",
        plan_name="Growth",
        amount_minor=2_500_000,
        currency="NGN",
        reference="ord_abc123",
    )

    assert "₦25,000" in message.body
    assert "ord_abc123" in message.body
    assert "Growth" in message.subject


def test_credentials_carry_the_secrets_and_say_they_cannot_be_resent(outbox):
    """Both secrets exist only in this message.

    The API key and the temporary password are stored as hashes, so there is
    nothing to look up later. The email has to say so — otherwise a customer who
    loses it asks for a copy that cannot exist.
    """
    message = credentials(
        to="buyer@example.com",
        company_name="Bright Dental",
        temporary_password="tmp-secret-123",
        api_key="nsk_live_SECRETKEY",
        widget_token="PUBLICTOKEN",
    )

    assert "tmp-secret-123" in message.body
    assert "nsk_live_SECRETKEY" in message.body
    assert "cannot send it again" in message.body
    assert "shown once and never again" in message.body


def test_credentials_include_a_pasteable_embed_snippet(outbox):
    """The customer's actual next step, not a link to documentation."""
    message = credentials(
        to="buyer@example.com",
        company_name="Bright Dental",
        temporary_password=None,
        api_key=None,
        widget_token="PUBLICTOKEN",
    )

    assert "widget.js" in message.body
    assert 'data-token="PUBLICTOKEN"' in message.body


def test_credentials_distinguish_the_public_token_from_the_secret_key(outbox):
    """A customer who confuses the two puts a credential in their page source."""
    message = credentials(
        to="buyer@example.com",
        company_name="Bright Dental",
        temporary_password=None,
        api_key="nsk_live_SECRETKEY",
        widget_token="PUBLICTOKEN",
    )

    assert "never in a web page" in message.body
    assert "safe in your page source" in message.body


@pytest.mark.parametrize("address", ["", "not-an-email"])
def test_an_unsendable_address_is_refused_when_the_message_is_built(address):
    """Caught at construction rather than at send.

    A bad address discovered inside the transport is an error with no context;
    here it names the field while the caller is still on the stack.
    """
    with pytest.raises(ValueError):
        Message(to=address, subject="Subject", body="Body")


def test_a_message_needs_a_subject():
    with pytest.raises(ValueError):
        Message(to="a@example.com", subject="   ", body="Body")


# ---------- delivering ----------


def test_a_failed_send_is_reported_rather_than_raised():
    """Provisioning must not roll back because a mail server had a bad minute.

    The money has already moved by then. A workspace that failed to save because
    its welcome email bounced is strictly worse than an email to resend.
    """

    class Broken(MemoryMailTransport):
        name = "broken"

        def _deliver(self, message):
            raise RuntimeError("smtp exploded")

    set_transport(Broken())
    try:
        from app.mail import send

        result = send(Message(to="a@example.com", subject="S", body="B"))
    finally:
        set_transport(None)

    assert result.sent is False
    assert "smtp exploded" in result.error


def test_an_unknown_backend_falls_back_instead_of_failing_to_start():
    """A typo in an env var should not take the whole app down."""
    assert build_transport("nonsense").name == "console"


def test_the_default_backend_logs_rather_than_sends():
    """So a fresh clone runs the purchase flow without mailing anyone."""
    assert build_transport(None).name == "console"


# ---------- the follow-up runner ----------


@pytest.fixture
def live_workspace(db):
    """A workspace that went live 40 days ago, so every rule is due."""
    now = datetime.now(timezone.utc)

    org = Organization(name="Bright Dental", slug="bright-dental")
    db.add(org)
    db.commit()
    db.refresh(org)

    order = Order(
        organization_id=org.id,
        paystack_reference="ord_followup",
        plan_code="starter",
        plan_name="Starter",
        billing_period="month",
        amount_minor=900_000,
        currency="NGN",
        buyer_email="owner@bright.example",
        buyer_company="Bright Dental",
        status=ORDER_PAID,
        paid_at=now - timedelta(days=40),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    profile = WorkspaceProfile(
        organization_id=org.id,
        order_id=order.id,
        plan_code="starter",
        role="sales_agent",
        status=PROVISION_READY,
        agent_name="Nera",
        company_name="Bright Dental",
        greeting="Hi",
        ready_at=now - timedelta(days=40),
        widget_token="tok_followup",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile, order, now


def test_the_runner_finds_what_is_owed_without_being_told_the_tenant(
    db, live_workspace, outbox
):
    """The first caller that legitimately spans tenants.

    FollowUpService.due is scoped to one organization because every earlier
    caller was serving one request for one org. Cron serves nobody, so it needs
    the cross-tenant query.
    """
    profile, order, now = live_workspace
    FollowUpService(db).schedule_for(profile, order)

    assert len(due_across_organizations(db, now=now)) > 0


def test_a_dry_run_sends_nothing(db, live_workspace, outbox):
    profile, order, now = live_workspace
    FollowUpService(db).schedule_for(profile, order)

    report = run_due(db, now=now, dry_run=True)

    assert report.due > 0
    assert outbox.outbox == []


def test_the_runner_delivers_and_does_not_send_twice(db, live_workspace, outbox):
    """Idempotence is the property that matters for anything cron calls.

    A second pass minutes later must not re-send what the first one delivered.
    """
    profile, order, now = live_workspace
    FollowUpService(db).schedule_for(profile, order)

    first = run_due(db, now=now, service=FollowUpService(db, sender=MailSender()))

    assert first.sent > 0
    assert first.sent + first.cancelled == first.due
    delivered = len(outbox.outbox)

    second = run_due(db, now=now, service=FollowUpService(db, sender=MailSender()))

    assert second.due == 0
    assert len(outbox.outbox) == delivered


def test_a_send_failure_leaves_the_follow_up_retryable(db, live_workspace):
    """The failure the Sender interface was designed around.

    A sender that swallowed the error would let the desk show a follow-up as
    sent that no customer received. It stays scheduled so the next run retries.
    """

    class Broken(MemoryMailTransport):
        name = "broken"

        def _deliver(self, message):
            raise RuntimeError("mail down")

    profile, order, now = live_workspace
    scheduled = FollowUpService(db).schedule_for(profile, order)

    set_transport(Broken())
    try:
        report = run_due(db, now=now, service=FollowUpService(db, sender=MailSender()))
    finally:
        set_transport(None)

    assert report.sent == 0
    assert report.failed > 0
    assert report.ok is False

    still_scheduled = [
        f for f in scheduled if f.status == STATUS_SCHEDULED
    ]
    assert still_scheduled, "a failed send must not consume the follow-up"


def test_the_mail_sender_raises_so_a_failure_is_not_recorded_as_sent():
    """MailSender's whole contract, tested directly."""

    class Broken(MemoryMailTransport):
        name = "broken"

        def _deliver(self, message):
            raise RuntimeError("nope")

    set_transport(Broken())
    try:
        with pytest.raises(FollowUpSendError):
            MailSender().send(
                Delivery(to_email="a@example.com", subject="S", body="B")
            )
    finally:
        set_transport(None)


def test_a_cancelled_follow_up_is_not_counted_as_a_failure(db, live_workspace, outbox):
    """send() cancels when a rule stops applying, which is a correct outcome.

    Counting it as failure would make cron exit non-zero on a healthy run.
    """
    profile, order, now = live_workspace
    FollowUpService(db).schedule_for(profile, order)

    report = run_due(db, now=now, service=FollowUpService(db, sender=MailSender()))

    assert report.cancelled >= 0
    assert report.failed == 0
    assert report.ok is True
