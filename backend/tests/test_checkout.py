"""Checkout and provisioning tests.

The money path and the thing money buys. Everything here runs against a fake
Paystack transport, which is the point: no account, no keys, no network, and
the failure modes that matter — a tampered amount, a forged webhook, a
retried delivery — can be produced on demand instead of waited for.

The adversarial cases are grouped at the bottom and are the reason this file
exists. A bug in the conversation costs a sale; a bug here costs money, or
gives away a workspace nobody paid for.
"""

import hashlib
import hmac
import json

import pytest

from app.catalog import PLANS, find_plan
from app.config.settings import settings
from app.models.order import ORDER_PAID, ORDER_PENDING, Order
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace_profile import (
    PROVISION_READY,
    PROVISION_STEPS,
    WorkspaceProfile,
)
from app.payments.checkout import CheckoutError, CheckoutService
from app.payments.paystack import (
    PaymentsNotConfigured,
    PaystackClient,
    PaystackError,
)
from app.payments.provisioning import ProvisioningService, hash_api_key

TEST_SECRET = "sk_test_pretend_key_for_tests"

DEFAULT_PLAN = next(p for p in PLANS if p.is_default)


class FakeTransport:
    """Stands in for Paystack.

    Records every request so tests can assert on what was actually sent —
    which is how the "amount comes from the catalog" property gets checked at
    the boundary rather than just in the service that computed it.
    """

    def __init__(self, paid: bool = True, amount_override: int | None = None):
        self.paid = paid
        self.amount_override = amount_override
        self.requests: list[dict] = []
        self.fail_initialize = False

    def request(self, method, url, *, headers, json_body=None):
        self.requests.append(
            {"method": method, "url": url, "headers": headers, "body": json_body}
        )

        if "/transaction/initialize" in url:
            if self.fail_initialize:
                return 400, {"status": False, "message": "Invalid amount"}

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
                    "status": "success" if self.paid else "abandoned",
                    "amount": (
                        self.amount_override
                        if self.amount_override is not None
                        else DEFAULT_PLAN.amount_minor
                    ),
                    "currency": DEFAULT_PLAN.currency,
                },
            }

        raise AssertionError(f"FakeTransport got an unexpected call: {method} {url}")

    @property
    def initialize_calls(self) -> list[dict]:
        return [r for r in self.requests if "/transaction/initialize" in r["url"]]


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def paystack(transport) -> PaystackClient:
    return PaystackClient(secret_key=TEST_SECRET, transport=transport)


@pytest.fixture
def storefront(db) -> Organization:
    org = Organization(name="NekoSalesAI Demo", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def checkout(db, paystack) -> CheckoutService:
    return CheckoutService(db, client=paystack)


def make_order(checkout, storefront, **overrides) -> Order:
    params = {
        "organization_id": storefront.id,
        "plan_code": DEFAULT_PLAN.code,
        "buyer_email": "buyer@example.com",
        "buyer_name": "Ada Buyer",
        "buyer_company": "Buyer Co",
    }
    params.update(overrides)
    return checkout.create_order(**params)


def signed(body: dict, secret: str = TEST_SECRET) -> tuple[bytes, str]:
    raw = json.dumps(body).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha512).hexdigest()
    return raw, signature


def charge_event(reference: str, amount_minor: int, currency: str = "NGN") -> dict:
    return {
        "event": "charge.success",
        "data": {
            "reference": reference,
            "status": "success",
            "amount": amount_minor,
            "currency": currency,
        },
    }


# ---------- creating an order ----------


def test_order_amount_comes_from_the_catalog_not_the_request(
    checkout, storefront, transport
):
    order = make_order(checkout, storefront)

    assert order.amount_minor == DEFAULT_PLAN.amount_minor
    assert order.currency == DEFAULT_PLAN.currency

    # And the same figure is what actually crossed the wire.
    sent = transport.initialize_calls[0]["body"]
    assert sent["amount"] == DEFAULT_PLAN.amount_minor
    assert sent["currency"] == DEFAULT_PLAN.currency


@pytest.mark.parametrize("plan", PLANS, ids=lambda p: p.code)
def test_every_plan_can_be_ordered_at_its_published_price(
    checkout, storefront, plan, transport
):
    order = make_order(checkout, storefront, plan_code=plan.code)

    assert order.amount_minor == plan.amount_minor
    assert order.plan_name == plan.name
    assert order.billing_period == plan.billing_period
    assert transport.initialize_calls[-1]["body"]["amount"] == plan.amount_minor


def test_order_starts_pending_with_a_checkout_url(checkout, storefront):
    order = make_order(checkout, storefront)

    assert order.status == ORDER_PENDING
    assert order.paid_at is None
    assert order.checkout_url.startswith("https://checkout.paystack.com/")


def test_unknown_plan_is_refused(checkout, storefront):
    with pytest.raises(CheckoutError):
        make_order(checkout, storefront, plan_code="enterprise_unlimited_free")


def test_order_without_an_email_is_refused(checkout, storefront):
    with pytest.raises(CheckoutError):
        make_order(checkout, storefront, buyer_email="   ")


def test_repeat_request_reuses_the_pending_order(checkout, storefront, transport):
    first = make_order(checkout, storefront)
    second = make_order(checkout, storefront)

    assert first.id == second.id
    assert len(transport.initialize_calls) == 1


def test_a_different_plan_gets_its_own_order(checkout, storefront):
    other = next(p for p in PLANS if p.code != DEFAULT_PLAN.code)

    first = make_order(checkout, storefront)
    second = make_order(checkout, storefront, plan_code=other.code)

    assert first.id != second.id


def test_missing_key_raises_payments_not_configured(db, storefront):
    service = CheckoutService(db, client=PaystackClient(secret_key="", transport=None))

    with pytest.raises(PaymentsNotConfigured):
        make_order(service, storefront)


def test_paystack_rejection_surfaces_as_paystack_error(db, storefront, transport):
    transport.fail_initialize = True
    service = CheckoutService(
        db, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
    )

    with pytest.raises(PaystackError):
        make_order(service, storefront)


# ---------- confirming payment ----------


def test_matching_charge_marks_the_order_paid(checkout, storefront, paystack):
    order = make_order(checkout, storefront)

    charge = paystack.charge_from_webhook(
        charge_event(order.paystack_reference, order.amount_minor)
    )
    confirmed = checkout.confirm(charge)

    assert confirmed.status == ORDER_PAID
    assert confirmed.paid_at is not None
    assert confirmed.provider_payload


def test_confirming_twice_does_not_change_anything(checkout, storefront, paystack):
    order = make_order(checkout, storefront)
    event = charge_event(order.paystack_reference, order.amount_minor)

    first = checkout.confirm(paystack.charge_from_webhook(event))
    paid_at = first.paid_at

    second = checkout.confirm(paystack.charge_from_webhook(event))

    assert second.id == first.id
    assert second.paid_at == paid_at


def test_unknown_reference_is_ignored(checkout, storefront, paystack):
    make_order(checkout, storefront)

    charge = paystack.charge_from_webhook(charge_event("neko_not_a_real_ref", 1))

    assert checkout.confirm(charge) is None


def test_non_charge_events_are_not_charges(paystack):
    assert paystack.charge_from_webhook({"event": "subscription.create"}) is None
    assert paystack.charge_from_webhook({"event": "charge.success"}) is None


# ---------- provisioning ----------


@pytest.fixture
def paid_order(checkout, storefront, paystack) -> Order:
    order = make_order(checkout, storefront)
    return checkout.confirm(
        paystack.charge_from_webhook(
            charge_event(order.paystack_reference, order.amount_minor)
        )
    )


def test_provisioning_creates_a_configured_workspace(db, paid_order):
    result = ProvisioningService(db).provision(paid_order)

    assert result.created is True
    assert result.profile.status == PROVISION_READY
    assert result.profile.plan_code == paid_order.plan_code
    assert result.profile.company_name == "Buyer Co"
    assert result.profile.agent_name
    assert result.profile.greeting


def test_provisioning_records_every_step(db, paid_order):
    result = ProvisioningService(db).provision(paid_order)
    stamps = json.loads(result.profile.steps_json)

    for step in PROVISION_STEPS:
        assert step in stamps, f"provisioning never recorded the {step!r} step"


def test_provisioning_issues_a_widget_token_and_an_api_key(db, paid_order):
    result = ProvisioningService(db).provision(paid_order)

    assert result.api_key.startswith("nsk_live_")
    assert result.profile.widget_token
    assert result.profile.api_key_prefix == result.api_key[:12]


def test_only_the_hash_of_the_api_key_is_stored(db, paid_order):
    result = ProvisioningService(db).provision(paid_order)
    profile = result.profile

    assert result.api_key not in (profile.api_key_hash or "")
    assert profile.api_key_hash == hash_api_key(result.api_key)

    # And nothing else on the row carries it either.
    stored = " ".join(
        str(getattr(profile, column.name)) for column in profile.__table__.columns
    )
    assert result.api_key not in stored


def test_provisioning_creates_an_admin_login_for_the_buyer(db, paid_order):
    result = ProvisioningService(db).provision(paid_order)

    user = db.query(User).filter(User.email == paid_order.buyer_email).first()

    assert user is not None
    assert user.is_admin is True
    assert user.organization_id == result.profile.organization_id
    assert result.temporary_password
    assert user.password_hash != result.temporary_password


def test_provisioning_is_idempotent(db, paid_order):
    service = ProvisioningService(db)

    first = service.provision(paid_order)
    second = service.provision(paid_order)

    assert second.created is False
    assert second.profile.id == first.profile.id
    assert db.query(WorkspaceProfile).count() == 1

    # The key is shown once. A second call does not reissue or re-reveal it.
    assert second.api_key is None


def test_workspace_is_separate_from_the_storefront_org(db, paid_order, storefront):
    result = ProvisioningService(db).provision(paid_order)

    assert result.profile.organization_id != storefront.id
    assert result.profile.organization.slug != storefront.slug


def test_unpaid_order_is_never_provisioned(db, checkout, storefront):
    order = make_order(checkout, storefront)

    with pytest.raises(ValueError):
        ProvisioningService(db).provision(order)

    assert db.query(WorkspaceProfile).count() == 0


def test_returning_buyer_does_not_get_their_password_reset(
    db, checkout, storefront, paystack
):
    """A second purchase from the same email must not touch the first login."""
    first = make_order(checkout, storefront)
    first = checkout.confirm(
        paystack.charge_from_webhook(
            charge_event(first.paystack_reference, first.amount_minor)
        )
    )
    ProvisioningService(db).provision(first)

    original_hash = (
        db.query(User).filter(User.email == first.buyer_email).first().password_hash
    )

    other = next(p for p in PLANS if p.code != DEFAULT_PLAN.code)
    second = make_order(checkout, storefront, plan_code=other.code)
    second = checkout.confirm(
        paystack.charge_from_webhook(
            charge_event(second.paystack_reference, second.amount_minor)
        )
    )
    result = ProvisioningService(db).provision(second)

    after = db.query(User).filter(User.email == first.buyer_email).first()

    assert after.password_hash == original_hash
    assert result.temporary_password is None


def test_rotating_the_key_invalidates_the_old_one(db, paid_order):
    service = ProvisioningService(db)
    result = service.provision(paid_order)

    rotated = service.rotate_api_key(result.profile)

    assert rotated != result.api_key
    assert result.profile.api_key_hash == hash_api_key(rotated)
    assert result.profile.api_key_hash != hash_api_key(result.api_key)


# ---------- adversarial ----------


def test_charge_for_less_than_the_order_is_refused(checkout, storefront, paystack):
    """The attack this exists for: pay ₦100, claim the ₦180,000 plan."""
    order = make_order(checkout, storefront)

    charge = paystack.charge_from_webhook(
        charge_event(order.paystack_reference, 100_00)
    )
    result = checkout.confirm(charge)

    assert result.status == ORDER_PENDING
    assert result.paid_at is None


def test_charge_in_a_different_currency_is_refused(checkout, storefront, paystack):
    order = make_order(checkout, storefront)

    charge = paystack.charge_from_webhook(
        charge_event(order.paystack_reference, order.amount_minor, currency="USD")
    )
    result = checkout.confirm(charge)

    assert result.status == ORDER_PENDING


def test_refused_charge_leaves_nothing_provisioned(db, checkout, storefront, paystack):
    order = make_order(checkout, storefront)

    checkout.confirm(
        paystack.charge_from_webhook(charge_event(order.paystack_reference, 1))
    )

    db.refresh(order)
    with pytest.raises(ValueError):
        ProvisioningService(db).provision(order)

    assert db.query(WorkspaceProfile).count() == 0


def test_failed_charge_status_leaves_the_order_pending(checkout, storefront, paystack):
    order = make_order(checkout, storefront)

    charge = paystack.charge_from_webhook(
        {
            "event": "charge.success",
            "data": {
                "reference": order.paystack_reference,
                "status": "failed",
                "amount": order.amount_minor,
                "currency": order.currency,
            },
        }
    )
    result = checkout.confirm(charge)

    assert result.status == ORDER_PENDING


def test_verification_disagreeing_with_the_order_is_refused(
    db, checkout, storefront, transport
):
    """confirm_by_reference must apply the same amount check as the webhook."""
    order = make_order(checkout, storefront)
    transport.amount_override = 50_00

    result = checkout.confirm_by_reference(order.paystack_reference)

    assert result.status == ORDER_PENDING


def test_abandoned_verification_does_not_mark_it_paid(db, checkout, storefront, transport):
    order = make_order(checkout, storefront)
    transport.paid = False

    result = checkout.confirm_by_reference(order.paystack_reference)

    assert result.status == ORDER_PENDING


# ---------- webhook signature ----------


def test_valid_signature_is_accepted(paystack):
    raw, signature = signed(charge_event("neko_abc", 1))
    assert paystack.verify_signature(raw, signature) is True


def test_forged_signature_is_rejected(paystack):
    raw, _ = signed(charge_event("neko_abc", 1))
    assert paystack.verify_signature(raw, "0" * 128) is False


def test_signature_from_a_different_secret_is_rejected(paystack):
    raw, signature = signed(charge_event("neko_abc", 1), secret="sk_test_someone_else")
    assert paystack.verify_signature(raw, signature) is False


def test_missing_signature_is_rejected(paystack):
    raw, _ = signed(charge_event("neko_abc", 1))
    assert paystack.verify_signature(raw, None) is False
    assert paystack.verify_signature(raw, "") is False


def test_tampered_body_invalidates_the_signature(paystack):
    """Signature is over the bytes, so editing the amount must break it."""
    event = charge_event("neko_abc", 100)
    raw, signature = signed(event)

    event["data"]["amount"] = 999_999_00
    tampered = json.dumps(event).encode("utf-8")

    assert paystack.verify_signature(tampered, signature) is False


def test_signature_check_fails_closed_without_a_key():
    """An unconfigured deployment must reject webhooks, not accept them."""
    raw, signature = signed(charge_event("neko_abc", 1))
    assert PaystackClient(secret_key="").verify_signature(raw, signature) is False


# ---------- HTTP surface ----------


def test_webhook_rejects_an_unsigned_request(client, storefront):
    response = client.post(
        "/api/v1/checkout/webhook",
        json=charge_event("neko_whatever", 1),
    )

    assert response.status_code == 401


def test_webhook_cannot_mark_an_order_paid_without_a_signature(
    client, checkout, storefront, db
):
    order = make_order(checkout, storefront)

    client.post(
        "/api/v1/checkout/webhook",
        json=charge_event(order.paystack_reference, order.amount_minor),
    )

    db.refresh(order)
    assert order.status == ORDER_PENDING


def test_checkout_config_reports_disabled_when_no_key_is_set(client):
    body = client.get("/api/v1/checkout/config").json()

    assert body["enabled"] is False
    assert body["live_mode"] is False


def test_creating_an_order_without_keys_returns_503_not_500(client, storefront):
    response = client.post(
        "/api/v1/checkout/orders",
        json={"plan_code": DEFAULT_PLAN.code, "email": "buyer@example.com"},
    )

    assert response.status_code == 503
    assert "charged" in response.json()["detail"].lower()


def test_order_status_404s_for_an_unknown_reference(client, storefront):
    assert client.get("/api/v1/checkout/orders/neko_nope").status_code == 404


def test_order_status_reports_the_order_and_no_workspace_while_pending(
    client, checkout, storefront
):
    order = make_order(checkout, storefront)

    body = client.get(f"/api/v1/checkout/orders/{order.paystack_reference}").json()

    assert body["order"]["status"] == ORDER_PENDING
    assert body["order"]["display_amount"] == find_plan(order.plan_code).display_price
    assert body["workspace"] is None


def test_order_status_never_leaks_the_provider_payload(client, checkout, storefront):
    order = make_order(checkout, storefront)

    body = client.get(f"/api/v1/checkout/orders/{order.paystack_reference}").json()

    assert "provider_payload" not in json.dumps(body)


def test_paid_order_status_returns_a_ready_workspace(client, db, paid_order):
    body = client.get(
        f"/api/v1/checkout/orders/{paid_order.paystack_reference}"
    ).json()

    assert body["order"]["status"] == ORDER_PAID
    assert body["workspace"]["status"] == PROVISION_READY
    assert all(step["done"] for step in body["workspace"]["steps"])


def test_api_key_is_not_returned_on_a_second_read(client, db, paid_order):
    first = client.get(
        f"/api/v1/checkout/orders/{paid_order.paystack_reference}"
    ).json()
    second = client.get(
        f"/api/v1/checkout/orders/{paid_order.paystack_reference}"
    ).json()

    assert first["workspace"]["api_key"]
    assert second["workspace"]["api_key"] is None
    assert second["workspace"]["temporary_password"] is None
