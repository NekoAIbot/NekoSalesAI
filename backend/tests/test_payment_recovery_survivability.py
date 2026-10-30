"""Comprehensive Payment Recovery and Failure Survivability Tests for NERA 2.0.

Exercises and verifies the 10 failure-resilience scenarios required by release criteria:
1. Verified successful transaction
2. Invalid webhook signature
3. Amount or currency mismatch
4. Duplicate webhook delivery
5. Missing browser return after payment
6. Delayed webhook delivery
7. Paystack verification API temporarily unavailable
8. Application restart while an order remains pending
9. Customer signs in later and retrieves their purchased product
10. Repeated recovery attempts do not duplicate provisioning
"""

import hmac
import hashlib
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.order import ORDER_PAID, ORDER_PENDING, Order
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace_profile import WorkspaceProfile
from app.payments.checkout import CheckoutService
from app.payments.delivery import DeliveryService
from app.payments.paystack import Charge, PaystackClient, PaystackError
from app.payments.provisioning import ProvisioningService
from app.pricing.complexity import (
    PRODUCT_SALES_AGENT,
    Requirement,
)
from app.pricing.quotes import QuoteService


@pytest.fixture
def storefront_org(db: Session) -> Organization:
    org = db.query(Organization).filter(Organization.slug == settings.STOREFRONT_ORG_SLUG).first()
    if not org:
        org = Organization(
            name="Nera Storefront",
            slug=settings.STOREFRONT_ORG_SLUG,
            created_at=datetime.now(timezone.utc),
        )
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


@pytest.fixture
def test_order(db: Session, storefront_org: Organization) -> Order:
    quote = QuoteService(db).issue(Requirement(product_type=PRODUCT_SALES_AGENT, monthly_conversations=500))
    checkout = CheckoutService(db)
    order = checkout.create_order(
        organization_id=storefront_org.id,
        quote_reference=quote.reference,
        buyer_email="survivable_buyer@nera.ai",
        buyer_company="Resilience Tech Corp",
    )
    return order


def _make_signed_webhook_payload(order: Order, amount: int = None, currency: str = "NGN"):
    payload = {
        "event": "charge.success",
        "data": {
            "reference": order.paystack_reference,
            "status": "success",
            "amount": amount if amount is not None else order.amount_minor,
            "currency": currency,
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "customer": {"email": order.buyer_email}
        }
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(settings.PAYSTACK_SECRET_KEY.encode("utf-8"), raw, hashlib.sha512).hexdigest()
    return raw, sig


# ==============================================================================
# 1. Verified Successful Transaction
# ==============================================================================
def test_01_verified_successful_transaction(client: TestClient, db: Session, test_order: Order):
    raw, sig = _make_signed_webhook_payload(test_order)
    res = client.post("/api/v1/checkout/webhook", content=raw, headers={"X-Paystack-Signature": sig})
    assert res.status_code == 200

    db.refresh(test_order)
    assert test_order.status == ORDER_PAID
    assert test_order.paid_at is not None

    profiles = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == test_order.id).all()
    assert len(profiles) == 1
    assert profiles[0].status == "ready"


# ==============================================================================
# 2. Invalid Webhook Signature
# ==============================================================================
def test_02_invalid_webhook_signature(client: TestClient, db: Session, test_order: Order):
    raw, _ = _make_signed_webhook_payload(test_order)
    res = client.post("/api/v1/checkout/webhook", content=raw, headers={"X-Paystack-Signature": "forged_hex_signature"})
    assert res.status_code == 401

    db.refresh(test_order)
    assert test_order.status == ORDER_PENDING
    assert test_order.paid_at is None

    profiles = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == test_order.id).all()
    assert len(profiles) == 0


# ==============================================================================
# 3. Amount or Currency Mismatch
# ==============================================================================
def test_03_amount_or_currency_mismatch(client: TestClient, db: Session, test_order: Order):
    # Underpayment: ₦50 less
    raw_under, sig_under = _make_signed_webhook_payload(test_order, amount=test_order.amount_minor - 5000)
    res = client.post("/api/v1/checkout/webhook", content=raw_under, headers={"X-Paystack-Signature": sig_under})
    assert res.status_code == 200  # Paystack ack convention

    db.refresh(test_order)
    assert test_order.status == ORDER_PENDING
    assert test_order.paid_at is None

    # Currency mismatch: USD instead of NGN
    raw_curr, sig_curr = _make_signed_webhook_payload(test_order, currency="USD")
    res2 = client.post("/api/v1/checkout/webhook", content=raw_curr, headers={"X-Paystack-Signature": sig_curr})
    assert res2.status_code == 200

    db.refresh(test_order)
    assert test_order.status == ORDER_PENDING


# ==============================================================================
# 4. Duplicate Webhook Delivery (Idempotency)
# ==============================================================================
def test_04_duplicate_webhook_delivery(client: TestClient, db: Session, test_order: Order):
    raw, sig = _make_signed_webhook_payload(test_order)
    res1 = client.post("/api/v1/checkout/webhook", content=raw, headers={"X-Paystack-Signature": sig})
    assert res1.status_code == 200

    # Replay same webhook
    res2 = client.post("/api/v1/checkout/webhook", content=raw, headers={"X-Paystack-Signature": sig})
    assert res2.status_code == 200

    profiles = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == test_order.id).all()
    assert len(profiles) == 1  # Exactly one provisioned profile


# ==============================================================================
# 5. Missing Browser Return After Payment (Reconciler Recovers)
# ==============================================================================
def test_05_missing_browser_return_after_payment(db: Session, test_order: Order):
    mock_charge = Charge(
        reference=test_order.paystack_reference,
        amount_minor=test_order.amount_minor,
        currency=test_order.currency,
        status="success",
        paid=True,
        channel="card",
        customer_email=test_order.buyer_email,
        paid_at=datetime.now(timezone.utc),
        raw={"status": "success", "reference": test_order.paystack_reference},
    )

    fake_client = MagicMock()
    fake_client.verify.return_value = mock_charge

    # Customer closed browser; reconciler runs independently
    delivery_service = DeliveryService(db, checkout=CheckoutService(db, client=fake_client))
    report = delivery_service.reconcile(verify_pending=True)

    assert report.newly_paid == 1
    assert report.provisioned == 1

    db.refresh(test_order)
    assert test_order.status == ORDER_PAID

    profiles = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == test_order.id).all()
    assert len(profiles) == 1


# ==============================================================================
# 6. Delayed Webhook Delivery (Return Polling Verifies First)
# ==============================================================================
def test_06_delayed_webhook_delivery(client: TestClient, db: Session, test_order: Order):
    mock_charge = Charge(
        reference=test_order.paystack_reference,
        amount_minor=test_order.amount_minor,
        currency=test_order.currency,
        status="success",
        paid=True,
        channel="card",
        customer_email=test_order.buyer_email,
        paid_at=datetime.now(timezone.utc),
        raw={"status": "success", "reference": test_order.paystack_reference},
    )

    with patch.object(PaystackClient, "verify", return_value=mock_charge):
        # 1. Customer returns and polls order status BEFORE webhook arrives
        res = client.get(f"/api/v1/checkout/orders/{test_order.paystack_reference}")
        assert res.status_code == 200
        data = res.json()
        assert data["order"]["status"] == ORDER_PAID
        assert data["workspace"] is not None

        db.refresh(test_order)
        assert test_order.status == ORDER_PAID

    # 2. Webhook arrives late
    raw, sig = _make_signed_webhook_payload(test_order)
    webhook_res = client.post("/api/v1/checkout/webhook", content=raw, headers={"X-Paystack-Signature": sig})
    assert webhook_res.status_code == 200

    profiles = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == test_order.id).all()
    assert len(profiles) == 1


# ==============================================================================
# 7. Paystack Verification API Temporarily Unavailable
# ==============================================================================
def test_07_paystack_verification_api_temporarily_unavailable(client: TestClient, db: Session, test_order: Order):
    with patch.object(PaystackClient, "verify", side_effect=PaystackError("API Timeout / 502")):
        res = client.get(f"/api/v1/checkout/orders/{test_order.paystack_reference}")
        assert res.status_code == 200
        data = res.json()
        # Must leave order in pending status, NEVER falsely mark paid
        assert data["order"]["status"] == ORDER_PENDING
        assert data["workspace"] is None

        db.refresh(test_order)
        assert test_order.status == ORDER_PENDING
        assert test_order.paid_at is None


# ==============================================================================
# 8. Application Restart While Order Remains Pending
# ==============================================================================
def test_08_application_restart_while_order_remains_pending(db: Session, test_order: Order):
    # Simulate pending order persisted before restart
    db.commit()
    order_ref = test_order.paystack_reference

    # Fresh session / services standing up after restart
    db.expire_all()
    reloaded_order = db.query(Order).filter(Order.paystack_reference == order_ref).one()
    assert reloaded_order.status == ORDER_PENDING

    mock_charge = Charge(
        reference=order_ref,
        amount_minor=reloaded_order.amount_minor,
        currency=reloaded_order.currency,
        status="success",
        paid=True,
        channel="card",
        customer_email=reloaded_order.buyer_email,
        paid_at=datetime.now(timezone.utc),
        raw={"status": "success"},
    )
    fake_client = MagicMock()
    fake_client.verify.return_value = mock_charge

    # Reconciler picks it up on startup
    report = DeliveryService(db, checkout=CheckoutService(db, client=fake_client)).reconcile()
    assert report.newly_paid == 1
    db.refresh(reloaded_order)
    assert reloaded_order.status == ORDER_PAID


# ==============================================================================
# 9. Customer Signs In Later and Retrieves Purchased Product
# ==============================================================================
def test_09_customer_signs_in_later_and_retrieves_purchased_product(client: TestClient, db: Session, test_order: Order):
    # Complete payment
    raw, sig = _make_signed_webhook_payload(test_order)
    client.post("/api/v1/checkout/webhook", content=raw, headers={"X-Paystack-Signature": sig})

    db.refresh(test_order)
    assert test_order.status == ORDER_PAID

    # Find the created customer user
    user = db.query(User).filter(User.email == test_order.buyer_email).first()
    assert user is not None

    # Issue JWT token for customer
    from jose import jwt
    token = jwt.encode({"sub": str(user.id)}, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    headers = {"Authorization": f"Bearer {token}"}

    # Retrieve customer orders
    orders_res = client.get("/api/v1/checkout/orders", headers=headers)
    assert orders_res.status_code == 200
    orders_data = orders_res.json()
    assert len(orders_data) >= 1
    found = [o for o in orders_data if o["reference"] == test_order.paystack_reference]
    assert len(found) == 1
    assert found[0]["status"] == ORDER_PAID

    # Retrieve workspace profiles
    profiles_res = client.get("/api/v1/organizations/workspace/profiles", headers=headers)
    assert profiles_res.status_code == 200
    profiles_data = profiles_res.json()
    assert len(profiles_data) >= 1
    assert profiles_data[0]["status"] == "ready"


# ==============================================================================
# 10. Repeated Recovery Attempts Do Not Duplicate Provisioning
# ==============================================================================
def test_10_repeated_recovery_attempts_do_not_duplicate_provisioning(client: TestClient, db: Session, test_order: Order):
    # Customer user exists
    user = User(
        email=test_order.buyer_email,
        full_name="Recovery User",
        organization_id=test_order.organization_id,
        password_hash="mock_hash",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    from jose import jwt
    token = jwt.encode({"sub": str(user.id)}, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    headers = {"Authorization": f"Bearer {token}"}

    mock_charge = Charge(
        reference=test_order.paystack_reference,
        amount_minor=test_order.amount_minor,
        currency=test_order.currency,
        status="success",
        paid=True,
        channel="card",
        customer_email=test_order.buyer_email,
        paid_at=datetime.now(timezone.utc),
        raw={"status": "success"},
    )

    with patch.object(PaystackClient, "verify", return_value=mock_charge):
        # First recovery call: verifies and provisions
        res1 = client.post(f"/api/v1/checkout/orders/{test_order.paystack_reference}/verify", headers=headers)
        assert res1.status_code == 200
        assert res1.json()["paid"] is True

        # Second recovery call: idempotent, does not duplicate
        res2 = client.post(f"/api/v1/checkout/orders/{test_order.paystack_reference}/verify", headers=headers)
        assert res2.status_code == 200
        assert res2.json()["paid"] is True

        # Third recovery call
        res3 = client.post(f"/api/v1/checkout/orders/{test_order.paystack_reference}/verify", headers=headers)
        assert res3.status_code == 200

    profiles = db.query(WorkspaceProfile).filter(WorkspaceProfile.order_id == test_order.id).all()
    assert len(profiles) == 1
