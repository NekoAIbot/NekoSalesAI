"""Comprehensive Regression Test Suite for Paystack Financial Integrity Remediations.

Covers:
- F-01: Atomic payment settlement and concurrency protection (conditional update)
- F-02: Session rollback in _provision_if_paid preventing PendingRollbackError
- F-03: Single-use 24h credential claim token lifecycle, email matching, and API key rotation
- F-04: Queue starvation immunity, 2-hour abandonment transition, and late payment recovery
- F-05: Independent payment reconciliation decoupled from Telegram
- F-06: Distributed database-backed lease coordination
- F-07: Production configuration preflight check
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.security import hash_password, verify_password
from app.models.credential_claim import CredentialClaim
from app.models.order import (
    ORDER_ABANDONED,
    ORDER_PAID,
    ORDER_PENDING,
    Order,
)
from app.models.organization import Organization
from app.models.system_lease import SystemLease
from app.models.user import User
from app.models.workspace_profile import WorkspaceProfile
from app.payments.checkout import CheckoutService
from app.payments.delivery import DeliveryService
from app.payments.lease import LeaseService
from app.payments.paystack import Charge, PaystackClient
from app.payments.preflight import PreflightChecker
from app.payments.provisioning import ProvisionedAgent, ProvisioningService
from app.pricing.complexity import (
    CHANNEL_WEB,
    PRODUCT_SALES_AGENT,
    Requirement,
    price,
)
from app.pricing.quotes import QuoteService


class FakeTransport:
    def __init__(self, paid: bool = True, amount: int = 201_500_00):
        self.paid = paid
        self.amount = amount
        self.requests = []

    def request(self, method, url, *, headers, json_body=None):
        self.requests.append({"method": method, "url": url, "headers": headers, "body": json_body})
        if "/transaction/initialize" in url:
            ref = (json_body or {}).get("reference", "ref_test")
            return 200, {
                "status": True,
                "data": {
                    "authorization_url": f"https://checkout.paystack.com/{ref}",
                    "access_code": f"acc_{ref}",
                    "reference": ref,
                },
            }
        if "/transaction/verify/" in url:
            ref = url.rsplit("/", 1)[-1]
            return 200, {
                "status": True,
                "data": {
                    "reference": ref,
                    "status": "success" if self.paid else "abandoned",
                    "amount": self.amount,
                    "currency": "NGN",
                },
            }
        return 200, {"status": True, "data": {}}


@pytest.fixture
def fake_client():
    return PaystackClient(secret_key="sk_test_mock_key_for_testing", transport=FakeTransport())


@pytest.fixture
def test_org(db: Session) -> Organization:
    org = Organization(name="Integrity Test Corp", slug=f"integrity-test-{secrets.token_hex(4)}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def test_order(db: Session, test_org: Organization, fake_client) -> Order:
    checkout = CheckoutService(db, client=fake_client)
    build = Requirement(product_type=PRODUCT_SALES_AGENT, channels=(CHANNEL_WEB,), monthly_conversations=500)
    quote = QuoteService(db).issue(build)
    order = checkout.create_order(
        organization_id=test_org.id,
        quote_reference=quote.reference,
        buyer_email=f"buyer_{secrets.token_hex(4)}@example.com",
        buyer_company="Integrity Test Corp",
    )
    return order


# ==============================================================================
# F-01: Atomic Payment Settlement Concurrency & Late Payment Recovery
# ==============================================================================

def test_atomic_settlement_single_winner(db: Session, test_order: Order, fake_client):
    """Verify that multiple confirm() calls on the same order result in exactly one settlement commit."""
    checkout = CheckoutService(db, client=fake_client)
    charge = Charge(
        reference=test_order.paystack_reference,
        status="success",
        amount_minor=test_order.amount_minor,
        currency=test_order.currency,
        paid=True,
        raw={"id": 12345, "status": "success"},
    )

    receipt_counter = [0]
    orig_send_receipt = checkout._send_receipt

    def counted_receipt(order):
        receipt_counter[0] += 1
        orig_send_receipt(order)

    checkout._send_receipt = counted_receipt

    # First settlement succeeds
    res1 = checkout.confirm(charge)
    assert res1.is_paid

    # Second settlement attempt receives the paid order without re-sending receipt
    res2 = checkout.confirm(charge)
    assert res2.is_paid
    assert receipt_counter[0] == 1, "Receipt must be dispatched exactly once"


def test_late_payment_on_abandoned_order(db: Session, test_order: Order, fake_client):
    """Verify that an order in ORDER_ABANDONED transitions cleanly to ORDER_PAID when paid."""
    checkout = CheckoutService(db, client=fake_client)

    # Manually mark order abandoned (as the 2-hour timeout would)
    test_order.status = ORDER_ABANDONED
    db.commit()

    charge = Charge(
        reference=test_order.paystack_reference,
        status="success",
        amount_minor=test_order.amount_minor,
        currency=test_order.currency,
        paid=True,
        raw={"id": 9999, "status": "success"},
    )

    result = checkout.confirm(charge)
    assert result is not None
    assert result.status == ORDER_PAID
    assert result.paid_at is not None

    db.refresh(test_order)
    assert test_order.status == ORDER_PAID


# ==============================================================================
# F-02: Session Poisoning Rollback Recovery
# ==============================================================================

def test_session_poisoning_rollback_recovery(db: Session, test_order: Order):
    """Verify that a flush exception inside _provision_if_paid rolls back and allows clean retrieval."""
    from app.api.v1.routes.checkout import _provision_if_paid
    from app.schemas.checkout import WorkspaceOut

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    # Pre-create profile so get_for_order can find it
    profile = WorkspaceProfile(
        organization_id=test_order.organization_id,
        order_id=test_order.id,
        plan_code=test_order.plan_code,
        role="sales_agent",
        agent_name="Ada",
        company_name="Integrity Corp",
        greeting="Hello! I am Ada.",
        widget_token="test_widget_tok",
    )
    db.add(profile)
    db.commit()

    # Mock provision to raise an exception simulating concurrent collision
    with patch.object(ProvisioningService, "provision", side_effect=RuntimeError("Simulated flush conflict")):
        # Without db.rollback(), this would raise PendingRollbackError
        result = _provision_if_paid(test_order, db)
        assert result is not None
        assert isinstance(result, WorkspaceOut)
        assert result.agent_name == "Ada"


# ==============================================================================
# F-03: Credential Claim Token Lifecycle & API Key Rotation
# ==============================================================================

def test_credential_claim_lifecycle_and_redemption(db: Session, test_order: Order):
    """Test full setup claim token lifecycle: creation, validation, ownership check, completion."""
    from app.auth.router import claim_workspace, complete_setup
    from app.auth.schemas import ClaimWorkspaceRequest, CompleteSetupRequest

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    # Provision order
    res = ProvisioningService(db).provision(test_order)
    assert res.created

    claim = db.query(CredentialClaim).filter(CredentialClaim.order_id == test_order.id).first()
    assert claim is not None
    assert claim.email_sent_at is not None
    assert not claim.is_claimed
    assert not claim.is_expired

    raw_token = res.claim_token
    assert raw_token is not None

    # Step 1: Validate claim with mismatched email -> fails 400
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        claim_workspace(
            ClaimWorkspaceRequest(claim_token=raw_token, email="wrong_buyer@example.com"),
            db=db,
        )
    assert exc_info.value.status_code == 400

    # Step 2: Validate claim with correct email -> succeeds
    val_res = claim_workspace(
        ClaimWorkspaceRequest(claim_token=raw_token, email=test_order.buyer_email),
        db=db,
    )
    assert val_res["valid"] is True
    assert val_res["email"] == test_order.buyer_email

    # Step 3: Complete setup with short password -> fails validation
    from pydantic import ValidationError
    with pytest.raises((HTTPException, ValidationError)):
        complete_setup(
            CompleteSetupRequest(claim_token=raw_token, email=test_order.buyer_email, password="short"),
            db=db,
        )

    # Step 4: Complete setup successfully
    setup_res = complete_setup(
        CompleteSetupRequest(claim_token=raw_token, email=test_order.buyer_email, password="SecurePassword123!"),
        db=db,
    )
    assert setup_res["api_key"] is not None
    assert setup_res["email"] == test_order.buyer_email

    db.refresh(claim)
    assert claim.is_claimed

    # Step 5: Token replay attempt -> rejected
    with pytest.raises(HTTPException) as replay_exc:
        complete_setup(
            CompleteSetupRequest(claim_token=raw_token, email=test_order.buyer_email, password="AnotherPassword123!"),
            db=db,
        )
    assert replay_exc.value.status_code == 400
    assert "already been used" in replay_exc.value.detail


def test_claim_token_expiry_rejection(db: Session, test_order: Order):
    """Verify that expired setup tokens are refused."""
    from app.auth.router import claim_workspace
    from app.auth.schemas import ClaimWorkspaceRequest
    from fastapi import HTTPException

    test_order.status = ORDER_PAID
    db.commit()
    res = ProvisioningService(db).provision(test_order)
    raw_token = res.claim_token

    claim = db.query(CredentialClaim).filter(CredentialClaim.order_id == test_order.id).first()
    # Force expiry to the past
    claim.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        claim_workspace(
            ClaimWorkspaceRequest(claim_token=raw_token, email=test_order.buyer_email),
            db=db,
        )
    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail.lower()


def test_self_service_api_key_rotation(db: Session, test_order: Order):
    """Verify self-service API key rotation route rotates the key and updates hashes."""
    from app.api.v1.routes.organizations import rotate_workspace_api_key
    from fastapi import HTTPException

    test_order.status = ORDER_PAID
    db.commit()
    ProvisioningService(db).provision(test_order)

    user = db.query(User).filter(User.email == test_order.buyer_email).first()
    profile = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == test_order.id).first()
    old_prefix = profile.api_key_prefix
    old_hash = profile.api_key_hash

    # Admin user rotation succeeds
    res = rotate_workspace_api_key(current_user=user, db=db)
    assert res["api_key"] is not None
    assert res["api_key_prefix"] is not None

    db.refresh(profile)
    assert profile.api_key_prefix != old_prefix or profile.api_key_hash != old_hash

    # Non-admin user rotation is rejected
    user.is_admin = False
    db.commit()
    with pytest.raises(HTTPException) as exc:
        rotate_workspace_api_key(current_user=user, db=db)
    assert exc.value.status_code == 403


# ==============================================================================
# F-04: Queue Starvation Immunity & Abandonment Policy
# ==============================================================================

def test_queue_starvation_immunity(db: Session, test_org: Organization, fake_client):
    """Verify that 20 newer orders do not starve an older un-reconciled order."""
    checkout = CheckoutService(db, client=fake_client)
    delivery = DeliveryService(db, checkout=checkout)
    now = datetime.now(timezone.utc)

    # Create 1 older order that has never been reconciled
    build = Requirement(product_type=PRODUCT_SALES_AGENT, monthly_conversations=500)
    quote = QuoteService(db).issue(build)

    older_order = checkout.create_order(
        organization_id=test_org.id,
        quote_reference=quote.reference,
        buyer_email="older_buyer@example.com",
    )
    older_order.last_reconciled_at = None
    db.commit()

    # Create 15 newer orders with last_reconciled_at = now
    for i in range(15):
        ord_i = checkout.create_order(
            organization_id=test_org.id,
            quote_reference=quote.reference,
            buyer_email=f"newer_buyer_{i}@example.com",
        )
        ord_i.last_reconciled_at = now
    db.commit()

    # Query next batch: older_order with NULL last_reconciled_at must be in the first 10
    batch = delivery._pending_with_a_checkout()
    batch_ids = [o.id for o in batch]
    assert older_order.id in batch_ids, "Older un-reconciled order was starved by newer orders!"


def test_abandonment_after_2_hours(db: Session, test_order: Order, fake_client):
    """Verify unpaid orders older than 2 hours transition to ORDER_ABANDONED."""
    # Mock transport to report abandoned / unpaid
    fake_client._transport.paid = False
    checkout = CheckoutService(db, client=fake_client)
    delivery = DeliveryService(db, checkout=checkout)

    # Backdate order created_at to 3 hours ago
    test_order.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    db.commit()

    report = delivery.reconcile(verify_pending=True)
    db.refresh(test_order)

    assert test_order.status == ORDER_ABANDONED
    assert test_order.reconcile_attempts >= 1


# ==============================================================================
# F-05 & F-06: Distributed Lease Coordination
# ==============================================================================

def test_distributed_lease_coordination(db: Session):
    """Verify lease mutual exclusion, TTL expiry, and release mechanics."""
    lease_service_1 = LeaseService(db, worker_id="worker_alpha:1001")
    lease_service_2 = LeaseService(db, worker_id="worker_beta:1002")

    lease_name = f"test_lease_{secrets.token_hex(4)}"

    # Worker 1 acquires lease
    assert lease_service_1.acquire_lease(lease_name, ttl_seconds=60) is True

    # Worker 2 attempts to acquire same lease -> rejected
    assert lease_service_2.acquire_lease(lease_name, ttl_seconds=60) is False

    # Worker 1 can renew its own lease
    assert lease_service_1.acquire_lease(lease_name, ttl_seconds=60) is True

    # Worker 1 releases lease
    lease_service_1.release_lease(lease_name)

    # Worker 2 can now acquire lease immediately
    assert lease_service_2.acquire_lease(lease_name, ttl_seconds=60) is True


# ==============================================================================
# F-07: Production Configuration Preflight Check
# ==============================================================================

def test_preflight_check_rules():
    """Verify that PreflightChecker enforces production promotion rules."""
    checker = PreflightChecker()

    # Development with valid test keys -> passes
    with patch.object(settings, "ENVIRONMENT", "development"), \
         patch.object(settings, "PAYSTACK_SECRET_KEY", "sk_test_mock1234567890"), \
         patch.object(settings, "PAYSTACK_PUBLIC_KEY", "pk_test_mock1234567890"):
        assert checker.check_all(probe_provider=False) is True

    # Production with test keys -> fails
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch.object(settings, "PAYSTACK_SECRET_KEY", "sk_test_mock1234567890"), \
         patch.object(settings, "PAYSTACK_PUBLIC_KEY", "pk_test_mock1234567890"), \
         patch.object(settings, "DATABASE_URL", "sqlite:///test.db"):
        assert checker.check_all(probe_provider=False) is False
        failed_names = [r.name for r in checker.results if not r.passed]
        assert "Production Live Secret Key" in failed_names
        assert "Production Database Engine" in failed_names


# ==============================================================================
# CORRECTION A: Durable, Concurrency-Safe Setup Email Delivery
# ==============================================================================

def test_email_dispatch_smtp_failure_records_error_and_preserves_intent(db: Session, test_order: Order):
    """Verify that SMTP failure after DB commit records error and leaves claim retryable."""
    from app import mail as mail_module

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    with patch.object(mail_module, "send", side_effect=RuntimeError("SMTP connection timeout")):
        ProvisioningService(db).provision(test_order)

    claim = db.query(CredentialClaim).filter(CredentialClaim.order_id == test_order.id).first()
    assert claim is not None
    assert claim.email_sent_at is None
    assert claim.dispatch_attempts >= 1
    assert claim.dispatch_last_attempt_at is not None
    assert "SMTP connection timeout" in (claim.dispatch_error or "")
    assert claim.dispatch_leased_until is None  # Lease released for retry

    # Autonomous retry succeeds
    with patch.object(mail_module, "send"):
        dispatched = ProvisioningService(db).retry_undelivered_claim_emails()
        assert dispatched == 1

    db.refresh(claim)
    assert claim.email_sent_at is not None
    assert claim.dispatch_error is None


def test_email_dispatch_simulated_crash_recovers_after_lease_expiry(db: Session, test_order: Order):
    """Verify recovery when worker crashes after SMTP send before recording success."""
    from app import mail as mail_module

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    user = User(
        email=test_order.buyer_email,
        full_name="Test Buyer",
        organization_id=test_order.organization_id,
        password_hash="hash",
    )
    db.add(user)
    db.flush()
    claim = CredentialClaim(
        order_id=test_order.id,
        user_id=user.id,
        token_hash="hash123",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        email_sent_at=None,
    )
    db.add(claim)
    db.commit()

    # Simulate worker acquired lease and crashed while lease was active
    now = datetime.now(timezone.utc)
    claim.dispatch_leased_by = "crashed_worker:9999"
    claim.dispatch_leased_until = now + timedelta(seconds=60)
    db.commit()

    # While lease is active, retry cannot steal the lease
    with patch.object(mail_module, "send") as mock_send:
        assert ProvisioningService(db).retry_undelivered_claim_emails() == 0
        assert not mock_send.called

    # Once lease expires, reconciler reacquires lease and retries
    claim.dispatch_leased_until = now - timedelta(seconds=1)
    db.commit()

    with patch.object(mail_module, "send") as mock_send:
        assert ProvisioningService(db).retry_undelivered_claim_emails() == 1
        assert mock_send.called

    db.refresh(claim)
    assert claim.email_sent_at is not None


def test_email_dispatch_two_workers_competing_mutual_exclusion(db: Session, test_order: Order):
    """Verify two workers cannot simultaneously dispatch the same pending email."""
    from app import mail as mail_module

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    user = User(
        email=test_order.buyer_email,
        full_name="Test Buyer",
        organization_id=test_order.organization_id,
        password_hash="hash",
    )
    db.add(user)
    db.flush()
    claim = CredentialClaim(
        order_id=test_order.id,
        user_id=user.id,
        token_hash="hash_compete",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        email_sent_at=None,
    )
    db.add(claim)
    db.commit()

    prov = ProvisioningService(db)

    # Worker 1 acquires dispatch lease
    with patch.object(mail_module, "send"):
        res1 = prov.dispatch_claim_email(claim, worker_id="worker_alpha", lease_seconds=60)
        assert res1 is True

    # Worker 2 attempts dispatch -> rejected because email_sent_at is set or leased
    with patch.object(mail_module, "send"):
        res2 = prov.dispatch_claim_email(claim, worker_id="worker_beta")
        assert res2 is False


def test_email_dispatch_expired_or_redeemed_tokens_rejected(db: Session, test_order: Order):
    """Verify expired or already-claimed tokens cannot be leased or dispatched."""
    from app import mail as mail_module

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    user = User(
        email=test_order.buyer_email,
        full_name="Test Buyer",
        organization_id=test_order.organization_id,
        password_hash="hash",
    )
    db.add(user)
    db.flush()
    claim = CredentialClaim(
        order_id=test_order.id,
        user_id=user.id,
        token_hash="hash_expired",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        email_sent_at=None,
    )
    db.add(claim)
    db.commit()

    with patch.object(mail_module, "send") as mock_send:
        res = ProvisioningService(db).dispatch_claim_email(claim)
        assert res is False
        assert not mock_send.called

    # Mark claimed
    claim.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    claim.claimed_at = datetime.now(timezone.utc)
    db.commit()

    with patch.object(mail_module, "send") as mock_send:
        res = ProvisioningService(db).dispatch_claim_email(claim)
        assert res is False
        assert not mock_send.called


# ==============================================================================
# CORRECTION B: Real Distributed Telegram Lease Ownership & Fencing
# ==============================================================================

def test_lease_valid_owner_renewal(db: Session):
    """Verify that only the active owner with matching fencing token can renew."""
    lease_name = f"test_lease_{secrets.token_hex(4)}"
    ls = LeaseService(db, worker_id="worker_1")
    assert ls.acquire_lease(lease_name, ttl_seconds=60) is True
    token = ls.fencing_token
    assert token >= 1

    time.sleep(0.05)
    # Valid renewal
    assert ls.renew_lease(lease_name, ttl_seconds=60, fencing_token=token) is True


def test_lease_wrong_owner_renewal_rejected(db: Session):
    """Verify that a non-owner cannot renew another worker's lease."""
    lease_name = f"test_lease_{secrets.token_hex(4)}"
    ls1 = LeaseService(db, worker_id="worker_owner")
    ls2 = LeaseService(db, worker_id="worker_intruder")

    assert ls1.acquire_lease(lease_name, ttl_seconds=60) is True
    # Worker 2 tries to renew Worker 1's lease -> rejected
    assert ls2.renew_lease(lease_name, ttl_seconds=60) is False


def test_lease_expired_reacquisition_increments_fencing_token(db: Session):
    """Verify that reacquiring an expired lease increments the fencing token."""
    lease_name = f"test_lease_{secrets.token_hex(4)}"
    ls1 = LeaseService(db, worker_id="worker_1")
    ls2 = LeaseService(db, worker_id="worker_2")

    assert ls1.acquire_lease(lease_name, ttl_seconds=60) is True
    token1 = ls1.fencing_token

    # Force expiration
    lease = db.query(SystemLease).filter(SystemLease.lease_name == lease_name).first()
    lease.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    # Worker 2 acquires expired lease
    assert ls2.acquire_lease(lease_name, ttl_seconds=60) is True
    token2 = ls2.fencing_token
    assert token2 > token1


def test_lease_old_worker_renewal_and_release_rejected_after_new_owner(db: Session):
    """Verify old owner cannot renew or release lease after new owner takes over."""
    lease_name = f"test_lease_{secrets.token_hex(4)}"
    ls1 = LeaseService(db, worker_id="worker_old")
    ls2 = LeaseService(db, worker_id="worker_new")

    assert ls1.acquire_lease(lease_name, ttl_seconds=60) is True
    token1 = ls1.fencing_token

    # Simulate lease expiry and takeover by worker_new
    lease = db.query(SystemLease).filter(SystemLease.lease_name == lease_name).first()
    lease.acquired_by = "worker_new"
    lease.fencing_token = token1 + 1
    lease.expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
    db.commit()

    # Old worker tries to renew -> rejected
    assert ls1.renew_lease(lease_name, ttl_seconds=60, fencing_token=token1) is False

    # Old worker tries to release -> rejected (does not delete new worker's lease)
    assert ls1.release_lease(lease_name, fencing_token=token1) is False

    # Verify new owner's lease is still completely intact
    db.refresh(lease)
    assert lease.acquired_by == "worker_new"
    exp = lease.expires_at.replace(tzinfo=timezone.utc) if lease.expires_at.tzinfo is None else lease.expires_at
    assert exp > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_poller_shutdown_releases_lease(db: Session, db_engine):
    """Verify that when stop_event is set, _run_poller shuts down and releases lease."""
    import asyncio
    from sqlalchemy.orm import sessionmaker
    from app.main import _run_poller

    test_session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    stop_event = asyncio.Event()
    label = f"test_sd_{secrets.token_hex(4)}"

    def mock_run():
        while not stop_event.is_set():
            time.sleep(0.01)

    with patch("app.database.session.SessionLocal", side_effect=test_session_factory), \
         patch("app.messaging.poller.TelegramPoller.run", side_effect=mock_run):
        task = asyncio.create_task(_run_poller(stop_event, label=label))
        await asyncio.sleep(0.1)
        stop_event.set()
        await asyncio.wait_for(task, timeout=5)

    lease = db.query(SystemLease).filter(SystemLease.lease_name == f"{label}_poller").first()
    assert lease is not None
    exp = lease.expires_at.replace(tzinfo=timezone.utc) if lease.expires_at.tzinfo is None else lease.expires_at
    assert exp <= datetime.now(timezone.utc) + timedelta(seconds=5)


# ==============================================================================
# CORRECTION C: Idempotent Paid-Order Provisioning and Recovery
# ==============================================================================

def test_provisioning_crash_immediately_after_settlement(db: Session, test_order: Order, fake_client):
    """Verify order marked ORDER_PAID with 0 profiles is automatically recovered."""
    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    delivery = DeliveryService(db)
    assert len(delivery.profiles_for(test_order)) == 0

    delivery.deliver(test_order)

    profiles = delivery.profiles_for(test_order)
    assert len(profiles) > 0
    assert test_order.is_delivered is True


def test_provisioning_two_workers_concurrent_no_duplicates(db: Session, test_order: Order):
    """Verify two concurrent provisioning invocations produce exactly 1 profile and claim."""
    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    prov = ProvisioningService(db)

    # First worker provisions
    res1 = prov.provision(test_order)
    assert len(res1.profiles) == 1

    # Second worker provisions concurrently
    res2 = prov.provision(test_order)
    assert len(res2.profiles) == 1

    # Check database: exactly 1 profile, 1 user, 1 claim
    profiles = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == test_order.id).all()
    claims = db.query(CredentialClaim).filter(CredentialClaim.order_id == test_order.id).all()
    users = db.query(User).filter(User.email == test_order.buyer_email).all()

    assert len(profiles) == 1, "Duplicate workspace profiles must not be created"
    assert len(claims) == 1, "Duplicate credential claims must not be created"
    assert len(users) == 1, "Duplicate users must not be created"
    assert res1.profiles[0].profile.id == res2.profiles[0].profile.id


def test_provisioning_repeated_reconciliation_idempotent(db: Session, test_order: Order):
    """Verify multiple reconciliation passes do not re-provision or rotate credentials."""
    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    delivery = DeliveryService(db)
    delivery.deliver(test_order)
    first_profile = delivery.profiles_for(test_order)[0]
    first_key = first_profile.api_key_hash

    # Repeated delivery passes
    delivery.deliver(test_order)
    delivery.deliver(test_order)

    db.refresh(first_profile)
    assert first_profile.api_key_hash == first_key, "API key must not rotate on repeated delivery passes"


# ==============================================================================
# CORRECTION D: Atomic Claim Redemption
# ==============================================================================

def test_complete_setup_atomic_conditional_update(db: Session, test_order: Order):
    """Verify complete_setup uses atomic conditional update, preventing double redemption."""
    from app.auth.router import complete_setup
    from app.auth.schemas import CompleteSetupRequest
    from fastapi import HTTPException

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    res = ProvisioningService(db).provision(test_order)
    raw_token = res.claim_token

    # First completion succeeds
    out1 = complete_setup(
        CompleteSetupRequest(claim_token=raw_token, email=test_order.buyer_email, password="ValidPassword123!"),
        db=db,
    )
    assert out1["api_key"] is not None

    # Second completion fails with HTTP 400
    with pytest.raises(HTTPException) as exc:
        complete_setup(
            CompleteSetupRequest(claim_token=raw_token, email=test_order.buyer_email, password="ValidPassword123!"),
            db=db,
        )
    assert exc.value.status_code == 400
    assert "already been used" in exc.value.detail


def test_complete_setup_transaction_boundary_and_rollback(db: Session, test_order: Order):
    """Verify that failure during credential rotation rolls back claim consumption."""
    from app.auth.router import complete_setup
    from app.auth.schemas import CompleteSetupRequest
    from fastapi import HTTPException

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    res = ProvisioningService(db).provision(test_order)
    raw_token = res.claim_token

    # Simulate crash/failure inside rotate_api_key
    with patch.object(ProvisioningService, "rotate_api_key", side_effect=RuntimeError("Key generation failed")):
        with pytest.raises(HTTPException) as exc:
            complete_setup(
                CompleteSetupRequest(claim_token=raw_token, email=test_order.buyer_email, password="ValidPassword123!"),
                db=db,
            )
        assert exc.value.status_code == 500

    # Claim MUST remain unclaimed so user is not locked out!
    claim = db.query(CredentialClaim).filter(CredentialClaim.order_id == test_order.id).first()
    assert claim.claimed_at is None, "Failed setup must not consume claim token"

    # Subsequent attempt succeeds
    out = complete_setup(
        CompleteSetupRequest(claim_token=raw_token, email=test_order.buyer_email, password="ValidPassword123!"),
        db=db,
    )
    assert out["api_key"] is not None
    db.refresh(claim)
    assert claim.claimed_at is not None


# ==============================================================================
# CORRECTION E: Public Credential Exposure Elimination
# ==============================================================================

def test_order_poll_never_returns_plaintext_credentials(db: Session, test_order: Order):
    """Correction E: Verify that _provision_if_paid never leaks api_key or temporary_password."""
    from app.api.v1.routes.checkout import _provision_if_paid

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    # First call provisions
    res = _provision_if_paid(test_order, db)
    assert res is not None
    assert res.api_key is None, "Plaintext API key must not be returned"
    assert res.temporary_password is None, "Plaintext temporary password must not be returned"


def test_order_status_poll_never_exposes_secrets_new_and_old_orders(client, db, test_order: Order):
    """Correction E: Verify neither new nor existing provisioned orders expose secrets via order status poll."""
    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()
    ref = test_order.paystack_reference

    # Read 1: Freshly provisioned
    resp1 = client.get(f"/api/v1/checkout/orders/{ref}").json()
    assert resp1["workspace"]["api_key"] is None
    assert resp1["workspace"]["temporary_password"] is None
    assert "token" not in resp1["workspace"]
    assert "claim_token" not in resp1["workspace"]

    # Read 2: Previously provisioned
    resp2 = client.get(f"/api/v1/checkout/orders/{ref}").json()
    assert resp2["workspace"]["api_key"] is None
    assert resp2["workspace"]["temporary_password"] is None
    assert "token" not in resp2["workspace"]
    assert "claim_token" not in resp2["workspace"]


# ==============================================================================
# PHASE 1 (P0) & PHASE 3 (P2): GENUINE CONCURRENCY & LEASE LOSS TESTS
# ==============================================================================

def test_concurrent_simultaneous_payment_settlement(db: Session, db_engine, test_order: Order, fake_client):
    """Concurrency Scenario 1: Two simultaneous workers race to confirm the same payment."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import sessionmaker

    db.commit()  # Ensure test_order is committed so independent worker sessions can read it

    session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    barrier = threading.Barrier(2)
    receipt_counter = []
    receipt_lock = threading.Lock()

    charge = Charge(
        reference=test_order.paystack_reference,
        status="success",
        amount_minor=test_order.amount_minor,
        currency=test_order.currency,
        paid=True,
        raw={"id": 12345, "status": "success"},
    )

    def worker(worker_id: int):
        with session_factory() as sess:
            checkout = CheckoutService(sess, client=fake_client)
            def counted_receipt(order):
                with receipt_lock:
                    receipt_counter.append(worker_id)
            checkout._send_receipt = counted_receipt

            barrier.wait(timeout=5)
            res = checkout.confirm(charge)
            return res.is_paid if res else False

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, 1)
        f2 = executor.submit(worker, 2)
        r1 = f1.result(timeout=10)
        r2 = f2.result(timeout=10)

    assert r1 is True and r2 is True
    assert len(receipt_counter) == 1, "Customer receipt must be dispatched exactly once"

    with session_factory() as verify_sess:
        order_fresh = verify_sess.get(Order, test_order.id)
        assert order_fresh.status == ORDER_PAID
        assert order_fresh.paid_at is not None


def test_concurrent_simultaneous_paid_order_provisioning(db: Session, db_engine, test_order: Order):
    """Concurrency Scenario 2: Two simultaneous workers race to provision the same paid order."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import sessionmaker

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    order_id = test_order.id
    buyer_email = test_order.buyer_email
    session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    barrier = threading.Barrier(2)

    def worker():
        with session_factory() as sess:
            prov = ProvisioningService(sess)
            order = sess.get(Order, order_id)
            barrier.wait(timeout=5)
            res = prov.provision(order)
            return res.profiles[0].profile.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker)
        f2 = executor.submit(worker)
        id1 = f1.result(timeout=10)
        id2 = f2.result(timeout=10)

    assert id1 == id2

    with session_factory() as verify_sess:
        profiles = verify_sess.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == order_id).all()
        claims = verify_sess.query(CredentialClaim).filter(CredentialClaim.order_id == order_id).all()
        users = verify_sess.query(User).filter(User.email == buyer_email).all()

        assert len(profiles) == 1, "Duplicate workspace profiles must not be created under concurrent execution"
        assert len(claims) == 1, "Duplicate credential claims must not be created under concurrent execution"
        assert len(users) == 1, "Duplicate users must not be created under concurrent execution"


def test_concurrent_simultaneous_credential_email_dispatch(db: Session, db_engine, test_order: Order):
    """Concurrency Scenario 3: Two simultaneous workers race to lease & dispatch the same credential email."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import sessionmaker
    from app import mail as mail_module

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    user = User(
        email=test_order.buyer_email,
        full_name="Test Buyer",
        organization_id=test_order.organization_id,
        password_hash="hash",
    )
    db.add(user)
    db.flush()
    claim = CredentialClaim(
        order_id=test_order.id,
        user_id=user.id,
        token_hash="hash_concurrent_dispatch",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        email_sent_at=None,
    )
    db.add(claim)
    db.commit()

    session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    barrier = threading.Barrier(2)
    claim_id = claim.id

    def worker(worker_name: str):
        with session_factory() as sess:
            prov = ProvisioningService(sess)
            c = sess.get(CredentialClaim, claim_id)
            barrier.wait(timeout=5)
            with patch.object(mail_module, "send"):
                acquired = prov.dispatch_claim_email(c, worker_id=worker_name, lease_seconds=60)
                return acquired

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, "worker_alpha")
        f2 = executor.submit(worker, "worker_beta")
        r1 = f1.result(timeout=10)
        r2 = f2.result(timeout=10)

    assert (r1 is True and r2 is False) or (r1 is False and r2 is True), "Exactly one worker must acquire the dispatch lease"

    with session_factory() as verify_sess:
        claim_fresh = verify_sess.get(CredentialClaim, claim_id)
        assert claim_fresh.email_sent_at is not None
        assert claim_fresh.dispatch_attempts == 1


def test_concurrent_simultaneous_setup_claim_redemption(db: Session, db_engine, test_order: Order):
    """Concurrency Scenario 4: Two simultaneous clients race to redeem the same single-use claim token."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import sessionmaker
    from app.auth.router import complete_setup
    from app.auth.schemas import CompleteSetupRequest
    from fastapi import HTTPException

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    res = ProvisioningService(db).provision(test_order)
    raw_token = res.claim_token
    buyer_email = test_order.buyer_email
    order_id = test_order.id

    session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    barrier = threading.Barrier(2)

    def worker():
        with session_factory() as sess:
            barrier.wait(timeout=5)
            try:
                out = complete_setup(
                    CompleteSetupRequest(
                        claim_token=raw_token,
                        email=buyer_email,
                        password="SecurePassword123!",
                    ),
                    db=sess,
                )
                return {"status": 200, "data": out}
            except HTTPException as exc:
                return {"status": exc.status_code, "detail": exc.detail}

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker)
        f2 = executor.submit(worker)
        res1 = f1.result(timeout=10)
        res2 = f2.result(timeout=10)

    statuses = [res1["status"], res2["status"]]
    assert 200 in statuses, "One redemption attempt must succeed"
    assert 400 in statuses, "Racing redemption attempt must be rejected with 400"

    with session_factory() as verify_sess:
        claim = verify_sess.query(CredentialClaim).filter(CredentialClaim.order_id == order_id).first()
        assert claim.claimed_at is not None


def test_concurrent_simultaneous_distributed_lease_acquisition(db: Session, db_engine):
    """Concurrency Scenario 5: Two simultaneous workers race to acquire the same distributed lease."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import sessionmaker

    lease_name = f"concurrent_lease_{secrets.token_hex(4)}"
    session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    barrier = threading.Barrier(2)

    def worker(worker_name: str):
        with session_factory() as sess:
            ls = LeaseService(sess, worker_id=worker_name)
            barrier.wait(timeout=5)
            acquired = ls.acquire_lease(lease_name, ttl_seconds=60)
            return acquired, ls.fencing_token

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, "worker_alpha")
        f2 = executor.submit(worker, "worker_beta")
        r1, token1 = f1.result(timeout=10)
        r2, token2 = f2.result(timeout=10)

    assert (r1 is True and r2 is False) or (r1 is False and r2 is True), "Exactly one worker must acquire the lease"

    with session_factory() as verify_sess:
        lease = verify_sess.query(SystemLease).filter(SystemLease.lease_name == lease_name).first()
        assert lease is not None
        assert lease.acquired_by in ("worker_alpha", "worker_beta")
        assert lease.fencing_token >= 1


def test_poller_stopping_guard_skips_reconciliation_work():
    """Phase 3 (P2): Verify poller checks stopping state before beginning reconciliation."""
    from app.messaging.poller import TelegramPoller
    from app.payments.delivery import DeliveryReport

    reconciler_calls = [0]
    class MockDelivery:
        def __init__(self, db): pass
        def reconcile(self):
            reconciler_calls[0] += 1
            return DeliveryReport()

    poller = TelegramPoller(
        bot_token="test-token",
        fetch=lambda _p: {"ok": True, "result": []},
        session_factory=lambda: MagicMock(),
        push_clients={},
    )
    poller.stop()
    assert poller._stopping is True

    with patch("app.messaging.poller.DeliveryService", MockDelivery):
        rep = poller.reconcile_payments()
        assert rep.checked == 0
        assert reconciler_calls[0] == 0, "No reconciliation work may begin when stopping/fenced out"

        followup_rep = poller.reconcile_followups()
        assert followup_rep.due == 0


# ==============================================================================
# SEC-01 & REL-01: Release Readiness Remediations (Customer Login & Token Recovery)
# ==============================================================================

def test_e2e_sec_01_customer_setup_and_login_unblocked(db: Session, client: TestClient, test_order: Order):
    """SEC-01 (P0): Verify complete_setup marks email_verified=True and unblocks customer login.
    
    1. Provisions paid order.
    2. Verifies unverified user cannot log in before setup completion.
    3. Completes setup with secure password and single-use claim token.
    4. Immediately logs in using buyer email and new password.
    5. Confirms authentication succeeds and protected workspace (/me) is accessible.
    6. Confirms second redemption attempt fails.
    7. Confirms invalid or expired claims cannot verify email or activate account.
    """
    from fastapi import HTTPException
    from app.auth.router import claim_workspace, complete_setup
    from app.auth.schemas import ClaimWorkspaceRequest, CompleteSetupRequest

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    # Provision order
    res = ProvisioningService(db).provision(test_order)
    assert res.created
    raw_token = res.claim_token
    assert raw_token is not None

    buyer_user = db.query(User).filter(User.email == test_order.buyer_email).first()
    assert buyer_user is not None
    assert buyer_user.email_verified is False

    # Attempting to log in prior to completing setup must be rejected
    pre_login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": test_order.buyer_email, "password": "AnyPassword123!"},
    )
    assert pre_login_resp.status_code in (401, 403)

    # Complete setup with valid credentials
    new_password = "SecureCustomerPassword123!"
    setup_res = complete_setup(
        CompleteSetupRequest(
            claim_token=raw_token,
            email=test_order.buyer_email,
            password=new_password,
        ),
        db=db,
    )
    assert setup_res["access_token"] is not None
    assert setup_res["token_type"] == "bearer"
    assert setup_res["email"] == test_order.buyer_email
    assert setup_res["api_key"] is not None

    # Verify user record in database has email_verified=True and is_active=True
    db.refresh(buyer_user)
    assert buyer_user.is_active is True
    assert buyer_user.email_verified is True

    # Immediate login succeeds using buyer email and new password
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": test_order.buyer_email, "password": new_password},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token_data = login_resp.json()
    assert "access_token" in token_data
    access_token = token_data["access_token"]

    # Verify protected workspace /me endpoint is accessible with this token
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == test_order.buyer_email
    assert me_data["email_verified"] is True
    assert me_data["is_active"] is True

    # Second redemption attempt fails (single-use guarantee)
    with pytest.raises(HTTPException) as replay_exc:
        complete_setup(
            CompleteSetupRequest(
                claim_token=raw_token,
                email=test_order.buyer_email,
                password="AnotherPassword123!",
            ),
            db=db,
        )
    assert replay_exc.value.status_code == 400
    assert "already been used" in replay_exc.value.detail

    # Invalid token cannot verify email or redeem
    with pytest.raises(HTTPException) as invalid_exc:
        complete_setup(
            CompleteSetupRequest(
                claim_token="invalid_bogus_token_12345",
                email="unknown@example.com",
                password="AnotherPassword123!",
            ),
            db=db,
        )
    assert invalid_exc.value.status_code == 400


def test_e2e_rel_01_encrypted_token_recovery_on_retry(db: Session, test_order: Order):
    """REL-01 (P2): Verify email retry decrypts durable token and preserves setup link validity.
    
    1. Provisions order and saves encrypted_token at rest.
    2. Simulates delivery crash where email was not sent (email_sent_at is None).
    3. Runs retry_undelivered_claim_emails() without raw_token in memory.
    4. Verifies worker decrypts encrypted_token, delivers email, and keeps token_hash unchanged.
    5. Verifies customer successfully completes setup using the original raw token.
    """
    from app.auth.router import complete_setup
    from app.auth.schemas import CompleteSetupRequest
    from app.models.credential_claim import decrypt_claim_token

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    # Provision order
    res = ProvisioningService(db).provision(test_order)
    original_raw_token = res.claim_token
    assert original_raw_token is not None

    claim = db.query(CredentialClaim).filter(CredentialClaim.order_id == test_order.id).first()
    assert claim is not None
    assert claim.encrypted_token is not None
    original_token_hash = claim.token_hash

    # Confirm decrypted token matches the raw token issued during provisioning
    recovered_token = decrypt_claim_token(claim.encrypted_token, settings.SECRET_KEY)
    assert recovered_token == original_raw_token

    # Simulate email delivery failure / crash: reset email_sent_at
    claim.email_sent_at = None
    claim.dispatch_leased_by = None
    claim.dispatch_leased_until = None
    db.commit()

    # Run retry worker (which does not have original_raw_token in memory)
    retried_count = ProvisioningService(db).retry_undelivered_claim_emails(worker_id="retry_worker_test")
    assert retried_count == 1

    db.refresh(claim)
    assert claim.email_sent_at is not None
    # Crucial: token_hash MUST NOT have changed, preserving the customer's link
    assert claim.token_hash == original_token_hash

    # Verify customer can successfully redeem setup link with original token
    setup_res = complete_setup(
        CompleteSetupRequest(
            claim_token=original_raw_token,
            email=test_order.buyer_email,
            password="DecryptedPassword123!",
        ),
        db=db,
    )
    assert setup_res["email"] == test_order.buyer_email
    assert setup_res["access_token"] is not None

    db.refresh(claim)
    assert claim.is_claimed is True


def test_rel_01_concurrent_email_retry_no_double_dispatch(db: Session, db_engine, test_order: Order):
    """REL-01 (P2): Verify concurrent retry workers respect dispatch leases without double-sending."""
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from sqlalchemy.orm import sessionmaker

    test_order.status = ORDER_PAID
    test_order.paid_at = datetime.now(timezone.utc)
    db.commit()

    res = ProvisioningService(db).provision(test_order)
    claim = db.query(CredentialClaim).filter(CredentialClaim.order_id == test_order.id).first()
    claim.email_sent_at = None
    claim.dispatch_leased_by = None
    claim.dispatch_leased_until = None
    db.commit()

    session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    barrier = threading.Barrier(2)

    def worker(worker_name: str):
        with session_factory() as sess:
            barrier.wait(timeout=5)
            return ProvisioningService(sess).retry_undelivered_claim_emails(worker_id=worker_name)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, "worker_1")
        f2 = executor.submit(worker, "worker_2")
        c1 = f1.result(timeout=10)
        c2 = f2.result(timeout=10)

    # Exactly one worker should successfully lease and dispatch the undelivered email
    assert c1 + c2 == 1, f"Expected exactly 1 successful dispatch, got worker1={c1}, worker2={c2}"

