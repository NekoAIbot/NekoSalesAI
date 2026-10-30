"""Tests for automated follow-up execution inside the poller.

Covers:
- Processing due follow-ups across multiple organizations.
- Throttling to prevent hammering the database on rapid poll cycles.
- Graceful exception handling so follow-up failures never crash Telegram polling.
- Preserving payment reconciliation and message polling alongside follow-ups.
- Delivery retryability: failed sends stay scheduled, successful sends transition to sent.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from app.followups.runner import RunReport, due_across_organizations, run_due
from app.followups.sender import MailSender
from app.followups.service import (
    CLAIM_TIMEOUT,
    FollowUpClaimConflict,
    FollowUpSendError,
    FollowUpService,
    _ensure_utc,
    reclaim_stale_claims,
)
from app.mail import MemoryMailTransport, set_transport
from app.messaging.poller import TelegramPoller
from app.models.follow_up import (
    STATUS_SCHEDULED,
    STATUS_SENDING,
    STATUS_SENT,
    FollowUp,
)
from app.models.order import ORDER_PAID, Order
from app.models.organization import Organization
from app.models.workspace_profile import PROVISION_READY, WorkspaceProfile


class _NullSession:
    """A session stand-in that is only opened and closed."""

    def close(self) -> None:
        pass


def _ok(*updates: dict) -> dict:
    return {"ok": True, "result": list(updates)}


def _make_workspace(
    db,
    *,
    org_name: str,
    slug: str,
    email: str,
    now: datetime,
) -> tuple[WorkspaceProfile, Order]:
    org = Organization(name=org_name, slug=slug)
    db.add(org)
    db.commit()
    db.refresh(org)

    order = Order(
        organization_id=org.id,
        paystack_reference=f"ord_{slug}",
        plan_code="starter",
        plan_name="Starter",
        billing_period="month",
        amount_minor=900_000,
        currency="NGN",
        buyer_email=email,
        buyer_company=org_name,
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
        company_name=org_name,
        greeting="Hi",
        ready_at=now - timedelta(days=40),
        widget_token=f"tok_{slug}",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile, order


# ---------- multi-tenant processing ----------


def test_due_followups_are_processed_across_organizations(db):
    """The poller must find and send owed follow-ups regardless of tenant."""
    now = datetime.now(timezone.utc)
    outbox = MemoryMailTransport()
    set_transport(outbox)

    try:
        p1, o1 = _make_workspace(
            db,
            org_name="Dental Alpha",
            slug="dental-alpha",
            email="owner@alpha.example",
            now=now,
        )
        p2, o2 = _make_workspace(
            db,
            org_name="Legal Beta",
            slug="legal-beta",
            email="owner@beta.example",
            now=now,
        )

        FollowUpService(db).schedule_for(p1, o1)
        FollowUpService(db).schedule_for(p2, o2)

        poller = TelegramPoller(
            bot_token="test-token",
            session_factory=lambda: db,
            followup_interval_seconds=0,
        )

        report = poller.reconcile_followups(now=now)

        assert report.due > 0
        assert report.sent > 0
        assert report.sent + report.cancelled == report.due

        recipients = {msg.to for msg in outbox.outbox}
        assert "owner@alpha.example" in recipients
        assert "owner@beta.example" in recipients

        # No follow-ups due at or before `now` remain scheduled
        due_left = due_across_organizations(db, now=now)
        assert len(due_left) == 0

        # And on a second pass, due count is 0 (idempotent / no duplicate send)
        second_report = poller.reconcile_followups(now=now, force=True)
        assert second_report.due == 0

    finally:
        set_transport(None)


# ---------- throttling ----------


def test_throttling_prevents_repeated_runner_invocations():
    """Rapid polling cycles must not repeatedly query or run follow-ups."""
    calls = {"count": 0}

    def counting_runner(db, **kwargs):
        calls["count"] += 1
        return RunReport(due=1, sent=1)

    poller = TelegramPoller(
        bot_token="test-token",
        session_factory=lambda: _NullSession(),
        followup_runner=counting_runner,
        followup_interval_seconds=300.0,
    )

    # First call: runs because initial timestamp is 0.0
    r1 = poller.reconcile_followups()
    assert calls["count"] == 1
    assert r1.sent == 1

    # Second call immediately after: throttled!
    r2 = poller.reconcile_followups()
    assert calls["count"] == 1
    assert r2.due == 0

    # Third call with force=True: bypasses throttle
    r3 = poller.reconcile_followups(force=True)
    assert calls["count"] == 2
    assert r3.sent == 1

    # Fourth call after advancing the clock past interval: runs
    poller._last_followup_check = time.monotonic() - 301.0
    r4 = poller.reconcile_followups()
    assert calls["count"] == 3
    assert r4.sent == 1


# ---------- exception safety ----------


def test_followup_exceptions_do_not_crash_poller(monkeypatch):
    """A database error or unhandled runner exception must not crash polling."""
    def exploding_runner(db, **kwargs):
        raise RuntimeError("database connection lost")

    poller = TelegramPoller(
        bot_token="test-token",
        fetch=lambda _p: _ok(),
        session_factory=lambda: _NullSession(),
        followup_runner=exploding_runner,
        followup_interval_seconds=0,
        push_clients={},
    )

    # Calling reconcile_followups directly returns a failed report without raising
    report = poller.reconcile_followups()
    assert report.failed == 1
    assert "database connection lost" in report.errors[0]

    # Running the poller one cycle finishes normally despite runner failure
    poll_report = poller.run(once=True)
    assert poll_report.updates == 0
    assert poll_report.failed == 0


def test_internal_type_error_in_runner_is_not_retried():
    """An internal TypeError inside runner must not trigger a second invocation."""
    calls = {"count": 0}

    def buggy_runner(db, **kwargs):
        calls["count"] += 1
        raise TypeError("internal bug: unsupported operand type")

    poller = TelegramPoller(
        bot_token="test-token",
        session_factory=lambda: _NullSession(),
        followup_runner=buggy_runner,
        followup_interval_seconds=0,
    )

    report = poller.reconcile_followups()
    assert calls["count"] == 1, "runner must be called exactly once, never retried on TypeError"
    assert report.failed == 1
    assert "internal bug" in report.errors[0]


def test_session_factory_failure_is_caught_safely():
    """Session creation explosion must be caught and reported, not crash."""
    def broken_factory():
        raise RuntimeError("database connection pool exhausted")

    poller = TelegramPoller(
        bot_token="test-token",
        fetch=lambda _p: _ok(),
        session_factory=broken_factory,
        followup_interval_seconds=0,
        push_clients={},
    )

    report = poller.reconcile_followups()
    assert report.failed == 1
    assert "connection pool exhausted" in report.errors[0]


def test_session_cleanup_failure_does_not_crash_poller():
    """A failure during session.close() must not escape to crash the poller."""
    class BadCloseSession:
        def close(self):
            raise RuntimeError("socket close failed")

    def ok_runner(db, **kwargs):
        return RunReport(due=1, sent=1)

    poller = TelegramPoller(
        bot_token="test-token",
        session_factory=lambda: BadCloseSession(),
        followup_runner=ok_runner,
        followup_interval_seconds=0,
    )

    report = poller.reconcile_followups()
    assert report.sent == 1


# ---------- integration in poll loop ----------


def test_payment_reconciliation_and_polling_remain_intact(monkeypatch):
    """The poller loop executes drain, payment reconciliation, and follow-ups."""
    from app.payments.delivery import DeliveryReport, Push

    runner_called = {"yes": False}

    def fake_followups(db, **kwargs):
        runner_called["yes"] = True
        return RunReport(due=0)

    class FakeDelivery:
        def __init__(self, db):
            pass

        def reconcile(self):
            return DeliveryReport(
                delivered=1,
                pushes=[Push(channel="telegram", external_id="123", text="Paid")],
            )

    monkeypatch.setattr("app.messaging.poller.DeliveryService", FakeDelivery)

    sent_pushes = []

    class FakeChat:
        def send_message(self, chat_id, text):
            sent_pushes.append((chat_id, text))

    poller = TelegramPoller(
        bot_token="test-token",
        fetch=lambda _p: _ok(),
        session_factory=lambda: _NullSession(),
        followup_runner=fake_followups,
        followup_interval_seconds=0,
        push_clients={"telegram": FakeChat()},
    )

    poll_report = poller.run(once=True)

    assert poll_report.updates == 0
    assert sent_pushes == [("123", "Paid")]
    assert runner_called["yes"] is True


# ---------- retryability and status transitions ----------


def test_failed_deliveries_remain_retryable_and_successful_records_transition(db):
    """Failed deliveries stay scheduled for retry; successful deliveries become sent."""
    now = datetime.now(timezone.utc)

    class BrokenTransport(MemoryMailTransport):
        name = "broken"

        def _deliver(self, message):
            raise RuntimeError("SMTP network unreachable")

    profile, order = _make_workspace(
        db,
        org_name="Retail Gamma",
        slug="retail-gamma",
        email="owner@gamma.example",
        now=now,
    )

    profile_id = profile.id
    FollowUpService(db).schedule_for(profile, order)

    poller = TelegramPoller(
        bot_token="test-token",
        session_factory=lambda: db,
        followup_interval_seconds=0,
    )

    # 1. Transport failure: follow-ups fail but remain scheduled
    set_transport(BrokenTransport())
    try:
        r1 = poller.reconcile_followups(now=now, force=True)
        assert r1.sent == 0
        assert r1.failed > 0
        assert r1.ok is False

        scheduled = (
            db.query(FollowUp)
            .filter(
                FollowUp.workspace_profile_id == profile_id,
                FollowUp.status == STATUS_SCHEDULED,
            )
            .all()
        )
        assert len(scheduled) > 0, "failed deliveries must remain scheduled"
    finally:
        set_transport(None)

    # 2. Working transport: follow-ups succeed and transition to STATUS_SENT
    working_outbox = MemoryMailTransport()
    set_transport(working_outbox)
    try:
        r2 = poller.reconcile_followups(now=now, force=True)
        assert r2.sent > 0
        assert r2.ok is True

        sent_rows = (
            db.query(FollowUp)
            .filter(
                FollowUp.workspace_profile_id == profile_id,
                FollowUp.status == STATUS_SENT,
            )
            .all()
        )
        assert len(sent_rows) > 0
        for row in sent_rows:
            assert row.sent_at is not None

        # 3. Third pass: already sent, so due count is 0 (idempotent / no duplicate send)
        r3 = poller.reconcile_followups(now=now, force=True)
        assert r3.due == 0
    finally:
        set_transport(None)


def test_concurrent_scheduler_send_prevented(db):
    """Two concurrent service instances trying to send the same follow-up will only deliver it once."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db,
        org_name="Concurrent Org",
        slug="concurrent-org",
        email="concurrent@example.com",
        now=now,
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]

    outbox = MemoryMailTransport()
    set_transport(outbox)

    try:
        service_a = FollowUpService(db, sender=MailSender())
        service_b = FollowUpService(db, sender=MailSender())

        # Instance A sends
        res_a = service_a.send(target)
        assert res_a.status == STATUS_SENT

        # Instance B attempts to send the same follow-up row concurrently
        with pytest.raises(Exception) as exc_info:
            service_b.send(target)
        assert "already" in str(exc_info.value).lower()

        # Exactly ONE message was delivered
        assert len(outbox.outbox) == 1
    finally:
        set_transport(None)


def test_crash_recovery_reclaims_stale_sending_followups(db):
    """A crashed worker that left a follow-up in STATUS_SENDING is reclaimed and retried after lease expiry."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db,
        org_name="Crashed Worker Org",
        slug="crashed-worker-org",
        email="recovered@example.com",
        now=now,
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]
    target_id = target.id

    # Simulate a crash 10 minutes ago where status was committed as STATUS_SENDING
    # but the process crashed before delivering or committing STATUS_SENT.
    stale_time = now - timedelta(minutes=10)
    db.query(FollowUp).filter(FollowUp.id == target_id).update(
        {"status": STATUS_SENDING, "updated_at": stale_time}
    )
    db.commit()

    outbox = MemoryMailTransport()
    set_transport(outbox)

    try:
        poller = TelegramPoller(
            bot_token="test-token",
            session_factory=lambda: db,
            followup_interval_seconds=0,
        )

        # Poller run detects the expired lease, reclaims it, and delivers successfully
        report = poller.reconcile_followups(now=now, force=True)
        assert report.sent > 0
        assert report.ok is True

        # Confirm the email was delivered
        recipients = {msg.to for msg in outbox.outbox}
        assert "recovered@example.com" in recipients

        # Confirm DB record is now STATUS_SENT
        row = db.query(FollowUp).filter(FollowUp.id == target_id).first()
        assert row.status == STATUS_SENT
        assert row.sent_at is not None
    finally:
        set_transport(None)


def test_active_in_flight_lease_blocks_concurrent_send(db):
    """An active, unexpired STATUS_SENDING claim cannot be intercepted by another worker."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db,
        org_name="In Flight Org",
        slug="in-flight-org",
        email="inflight@example.com",
        now=now,
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]
    target_id = target.id

    # Active lease acquired 10 seconds ago (well within the 5-minute lease)
    active_time = now - timedelta(seconds=10)
    db.query(FollowUp).filter(FollowUp.id == target_id).update(
        {"status": STATUS_SENDING, "updated_at": active_time}
    )
    db.commit()

    outbox = MemoryMailTransport()
    set_transport(outbox)

    try:
        service_b = FollowUpService(db, sender=MailSender())
        target_reloaded = db.query(FollowUp).filter(FollowUp.id == target_id).first()

        with pytest.raises(Exception) as exc_info:
            service_b.send(target_reloaded)
        assert "in-flight" in str(exc_info.value).lower() or "already" in str(exc_info.value).lower()

        # No email sent by the second worker
        assert len(outbox.outbox) == 0
    finally:
        set_transport(None)


def test_failed_send_resets_status_to_scheduled(db):
    """If delivery raises an exception, the status is immediately reset to scheduled rather than stuck in sending."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db,
        org_name="Failing Org",
        slug="failing-org",
        email="failing@example.com",
        now=now,
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]
    target_id = target.id

    class FailingSender:
        def send(self, delivery):
            raise RuntimeError("Outbound SMTP failure")

    failing_service = FollowUpService(db, sender=FailingSender())

    with pytest.raises(RuntimeError, match="Outbound SMTP failure"):
        failing_service.send(target)

    # Record must be back to STATUS_SCHEDULED, never stuck in STATUS_SENDING
    row = db.query(FollowUp).filter(FollowUp.id == target_id).first()
    assert row.status == STATUS_SCHEDULED
    assert row.sent_at is None


def test_stale_worker_cannot_overwrite_newer_worker_state(db):
    """If a slow worker's lease expired and was completed by another worker, the slow worker cannot overwrite it."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db,
        org_name="Stale Worker Org",
        slug="stale-worker-org",
        email="stale@example.com",
        now=now,
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]
    target_id = target.id

    class SlowFailingSender:
        def __init__(self, db_session, row_id):
            self._db = db_session
            self._row_id = row_id

        def send(self, delivery):
            # While this slow worker is executing send(), simulate Worker B reclaiming
            # the expired lease and successfully completing the delivery.
            self._db.query(FollowUp).filter(FollowUp.id == self._row_id).update(
                {
                    "status": STATUS_SENT,
                    "sent_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._db.commit()
            # Now slow Worker A fails with an error
            raise RuntimeError("Slow worker network timeout")

    sender = SlowFailingSender(db, target_id)
    service_a = FollowUpService(db, sender=sender)

    with pytest.raises(RuntimeError, match="Slow worker network timeout"):
        service_a.send(target)

    # Worker A's failure must NOT overwrite Worker B's STATUS_SENT back to STATUS_SCHEDULED
    row = db.query(FollowUp).filter(FollowUp.id == target_id).first()
    assert row.status == STATUS_SENT
    assert row.sent_at is not None


# ---------- Lease expiry, concurrent reclamation & runner accounting regression tests ----------


def test_slow_send_exceeding_lease_salvaged_if_unclaimed(db):
    """A send that takes longer than CLAIM_TIMEOUT and was reclaimed is safely salvaged into STATUS_SENT if unclaimed."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db,
        org_name="Slow Send Org",
        slug="slow-send-org",
        email="slowsend@example.com",
        now=now,
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]
    target_id = target.id

    class SlowSuccessfulSender:
        def __init__(self, db_session, row_id):
            self._db = db_session
            self._row_id = row_id

        def send(self, delivery):
            # Simulate the passage of 6 minutes (> CLAIM_TIMEOUT = 5m), causing
            # reclamation back to STATUS_SCHEDULED while this worker is still sending.
            reclaim_time = datetime.now(timezone.utc)
            self._db.query(FollowUp).filter(FollowUp.id == self._row_id).update(
                {
                    "status": STATUS_SCHEDULED,
                    "updated_at": reclaim_time,
                }
            )
            self._db.commit()

    sender = SlowSuccessfulSender(db, target_id)
    service_a = FollowUpService(db, sender=sender)

    result = service_a.send(target)

    # Worker A successfully salvaged the row into STATUS_SENT because no competing worker claimed it.
    assert result.status == STATUS_SENT
    assert result.sent_at is not None

    row = db.query(FollowUp).filter(FollowUp.id == target_id).first()
    assert row.status == STATUS_SENT
    assert row.sent_at is not None

    # Subsequent due check sees 0 owed follow-ups for this rule (no duplicate delivery)
    assert len(service.due(profile.organization_id, now=now)) == len(due_list) - 1


def test_second_worker_reclaims_and_sends_while_first_sender_active(db):
    """If a second worker reclaims and completes delivery while the first is slow, first worker preserves the state."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db,
        org_name="Competing Worker Org",
        slug="competing-worker-org",
        email="competing@example.com",
        now=now,
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]
    target_id = target.id

    worker_b_sent_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    class SlowSenderSurpassedByWorkerB:
        def __init__(self, db_session, row_id):
            self._db = db_session
            self._row_id = row_id

        def send(self, delivery):
            # Worker B claimed and completed the follow-up while Worker A was slow
            self._db.query(FollowUp).filter(FollowUp.id == self._row_id).update(
                {
                    "status": STATUS_SENT,
                    "sent_at": worker_b_sent_at,
                    "updated_at": worker_b_sent_at,
                }
            )
            self._db.commit()

    sender = SlowSenderSurpassedByWorkerB(db, target_id)
    service_a = FollowUpService(db, sender=sender)

    result = service_a.send(target)

    # State remains STATUS_SENT and Worker B's sent_at is preserved
    assert result.status == STATUS_SENT
    assert _ensure_utc(result.sent_at) == worker_b_sent_at

    row = db.query(FollowUp).filter(FollowUp.id == target_id).first()
    assert row.status == STATUS_SENT
    assert _ensure_utc(row.sent_at) == worker_b_sent_at


def test_stale_worker_finishing_while_competing_worker_sending(db):
    """If a stale worker finishes after a second worker claimed an active lease, first worker raises FollowUpClaimConflict."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db,
        org_name="InFlight Contention Org",
        slug="inflight-contention-org",
        email="inflightcontention@example.com",
        now=now,
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]
    target_id = target.id

    worker_b_lease_time = datetime.now(timezone.utc)

    class SlowSenderWorkerBClaimed:
        def __init__(self, db_session, row_id):
            self._db = db_session
            self._row_id = row_id

        def send(self, delivery):
            # Worker B reclaimed and actively acquired a lease
            self._db.query(FollowUp).filter(FollowUp.id == self._row_id).update(
                {
                    "status": STATUS_SENDING,
                    "updated_at": worker_b_lease_time,
                }
            )
            self._db.commit()

    sender = SlowSenderWorkerBClaimed(db, target_id)
    service_a = FollowUpService(db, sender=sender)

    with pytest.raises(FollowUpClaimConflict, match="claimed by another worker"):
        service_a.send(target)

    # Worker B's lease remains intact
    row = db.query(FollowUp).filter(FollowUp.id == target_id).first()
    assert row.status == STATUS_SENDING
    assert _ensure_utc(row.updated_at) == worker_b_lease_time


def test_concurrent_runner_accounting_benign_contention(db):
    """The runner records concurrent in-flight claims as benign contention, not delivery failures."""
    now = datetime.now(timezone.utc)
    profile_1, order_1 = _make_workspace(
        db, org_name="Org 1", slug="org-1", email="org1@example.com", now=now
    )
    profile_2, order_2 = _make_workspace(
        db, org_name="Org 2", slug="org-2", email="org2@example.com", now=now
    )
    service = FollowUpService(db)
    service.schedule_for(profile_1, order_1)
    service.schedule_for(profile_2, order_2)

    # Pick 2 due follow-ups
    all_due = due_across_organizations(db, now=now)
    assert len(all_due) >= 2
    f1, f2 = all_due[0], all_due[1]

    calls = {"f1": 0, "f2": 0}

    class MockWorkerService:
        def send(self, fu):
            if fu.id == f1.id:
                calls["f1"] += 1
                raise FollowUpClaimConflict("This follow-up is already being processed")
            if fu.id == f2.id:
                calls["f2"] += 1
                fu.status = STATUS_SENT
                return fu
            fu.status = STATUS_SENT
            return fu

    report = run_due(db, now=now, service=MockWorkerService())

    # Contention on f1 was counted as in_flight, not failed!
    assert report.in_flight >= 1
    assert report.failed == 0
    assert report.ok is True
    assert "in-flight" in report.summary()


def test_runner_never_classifies_status_sending_as_cancelled(db):
    """If send() returns a row with STATUS_SENDING, it must be counted as in_flight, never cancelled."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db, org_name="Sending Org", slug="sending-org", email="sending@example.com", now=now
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    class SendingWorkerService:
        def send(self, fu):
            fu.status = STATUS_SENDING
            return fu

    report = run_due(db, now=now, service=SendingWorkerService())
    assert report.cancelled == 0
    assert report.in_flight == report.due
    assert report.failed == 0
    assert report.ok is True


def test_recovery_after_process_interruption_and_delivery_failure(db):
    """Simulate a worker crash mid-lease, reclamation after timeout, and retry success."""
    now = datetime.now(timezone.utc)
    profile, order = _make_workspace(
        db, org_name="Recovery Org", slug="recovery-org", email="recovery@example.com", now=now
    )
    service = FollowUpService(db)
    service.schedule_for(profile, order)

    due_list = service.due(profile.organization_id, now=now)
    assert len(due_list) > 0
    target = due_list[0]
    target_id = target.id

    # 1. Simulate worker crash leaving row in STATUS_SENDING 6 minutes ago
    crashed_time = now - timedelta(minutes=6)
    db.query(FollowUp).filter(FollowUp.id == target_id).update(
        {"status": STATUS_SENDING, "updated_at": crashed_time}
    )
    db.commit()

    # 2. Stale claims are reclaimed
    reclaimed_count = reclaim_stale_claims(db, now=now, timeout=CLAIM_TIMEOUT)
    assert reclaimed_count >= 1

    row = db.query(FollowUp).filter(FollowUp.id == target_id).first()
    assert row.status == STATUS_SCHEDULED

    # 3. Next runner pass retries and successfully delivers
    outbox = MemoryMailTransport()
    set_transport(outbox)
    try:
        service_real = FollowUpService(db, sender=MailSender())
        result = service_real.send(row)
        assert result.status == STATUS_SENT
        assert len(outbox.outbox) == 1
    finally:
        set_transport(None)



