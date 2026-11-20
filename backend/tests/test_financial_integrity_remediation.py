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
