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
from sqlalchemy.exc import IntegrityError

from app.catalog import find_plan
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
from app.pricing.complexity import (
    CHANNEL_WEB,
    CHANNEL_WHATSAPP,
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    Requirement,
    price,
)
from app.pricing.quotes import QuoteService, plan_code_for
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT

TEST_SECRET = "sk_test_pretend_key_for_tests"


# What the storefront now sells: a build described by the buyer and priced by
# the engine. There is no default tier to order any more, so the tests order the
# way a buyer does — every amount below is computed from these requirements
# rather than written down, so a pricing change cannot leave a test asserting a
# figure the product no longer charges.
SALES_BUILD = Requirement(
    product_type=PRODUCT_SALES_AGENT,
    channels=(CHANNEL_WEB,),
    monthly_conversations=2_000,
)

# A deliberately different build, for the tests that need two distinct orders.
# Different product *and* different price, so "the second order is its own
# order" is not accidentally true only because of the amount.
SUPPORT_BUILD = Requirement(
    product_type=PRODUCT_SUPPORT_AGENT,
    channels=(CHANNEL_WEB, CHANNEL_WHATSAPP),
    monthly_conversations=500,
)

# The priced form of each, so a test can say what it expects without repeating
# the pricing rules. price() is the same function the checkout calls.
SALES_QUOTE = price(SALES_BUILD)
SUPPORT_QUOTE = price(SUPPORT_BUILD)

BUILDS = (SALES_BUILD, SUPPORT_BUILD)


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
                        else SALES_QUOTE.total_minor
                    ),
                    "currency": SALES_QUOTE.currency,
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


@pytest.fixture
def quoted(db) -> str:
    """A stored quote for the default build, as the conversation would issue it.

    Returns the reference. This is the storefront's only route to a payment now:
    the buyer describes a build, the engine prices it, and the reference names
    that requirement — never the amount.
    """
    return QuoteService(db).issue(SALES_BUILD).reference


def make_order(checkout, storefront, quoted=None, build=None, **overrides) -> Order:
    """Place an order the way the storefront does — against a quote.

    ``quoted`` is an existing reference and ``build`` a requirement to quote
    fresh; with neither, the default sales build is quoted. Overriding
    ``plan_code`` is still possible and a few tests do it deliberately, to prove
    a retired tier code is refused rather than silently priced.
    """
    params = {
        "organization_id": storefront.id,
        "buyer_email": "buyer@example.com",
        "buyer_name": "Ada Buyer",
        "buyer_company": "Buyer Co",
    }
    params.update(overrides)

    if not params.get("plan_code"):
        if quoted is None:
            quoted = QuoteService(checkout.db).issue(build or SALES_BUILD).reference
        params["quote_reference"] = quoted

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


def test_order_amount_is_computed_server_side_not_sent_by_the_caller(
    checkout, storefront, transport
):
    """The amount is never a parameter. It is re-derived from the requirement.

    This is the property the whole money path rests on: ``create_order`` takes a
    quote reference, and the figure that reaches Paystack is what
    ``price()`` returns for the requirement stored under it.
    """
    order = make_order(checkout, storefront)

    assert order.amount_minor == SALES_QUOTE.total_minor
    assert order.currency == SALES_QUOTE.currency

    # And the same figure is what actually crossed the wire.
    sent = transport.initialize_calls[0]["body"]
    assert sent["amount"] == SALES_QUOTE.total_minor
    assert sent["currency"] == SALES_QUOTE.currency


@pytest.mark.parametrize("build", BUILDS, ids=lambda b: b.product_type)
def test_every_build_can_be_ordered_at_its_computed_price(
    checkout, storefront, build, transport
):
    expected = price(build)

    order = make_order(checkout, storefront, build=build)

    assert order.amount_minor == expected.total_minor
    assert order.plan_name == expected.product_name
    assert order.billing_period == expected.billing_period
    assert transport.initialize_calls[-1]["body"]["amount"] == expected.total_minor


def test_order_starts_pending_with_a_checkout_url(checkout, storefront):
    order = make_order(checkout, storefront)

    assert order.status == ORDER_PENDING
    assert order.paid_at is None
    assert order.checkout_url.startswith("https://checkout.paystack.com/")


def test_unknown_plan_is_refused(checkout, storefront):
    with pytest.raises(CheckoutError):
        make_order(checkout, storefront, plan_code="enterprise_unlimited_free")


def test_retired_tier_codes_are_refused_not_re_priced(checkout, storefront):
    """The old storefront tiers are gone, and asking for one by name must fail.

    These three codes were real and public. A buyer, a bookmark or a stale
    cached page can still send them, and the only safe answer is a refusal —
    falling back to any other price would charge somebody for a plan this
    product no longer sells.
    """
    for retired in ("founding_annual", "growth_monthly", "starter_monthly"):
        with pytest.raises(CheckoutError):
            make_order(checkout, storefront, plan_code=retired)


def test_order_without_an_email_is_refused(checkout, storefront):
    with pytest.raises(CheckoutError):
        make_order(checkout, storefront, buyer_email="   ")


def test_repeat_request_reuses_the_pending_order(checkout, storefront, transport, quoted):
    """The same quote, asked for twice, is one order.

    Same *quote*, not merely the same build: a buyer who refreshes is redeeming
    the reference they were given. Two separate quotes for identical
    requirements are two things bought, and stacking them is correct.
    """
    first = make_order(checkout, storefront, quoted=quoted)
    second = make_order(checkout, storefront, quoted=quoted)

    assert first.id == second.id
    assert len(transport.initialize_calls) == 1


def test_a_different_build_gets_its_own_order(checkout, storefront):
    first = make_order(checkout, storefront)
    second = make_order(checkout, storefront, build=SUPPORT_BUILD)

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


# ---------- delivering a two-product purchase ----------
#
# Everything above provisions a single-product order, and every two-product test
# in this file stops at the order. The join between them was never walked, and
# the bug living in it was total: ``workspace_profiles.organization_id`` was
# unique, from when a purchase meant one agent, so provisioning a paid
# two-product order created one organization, wrote the first profile, and had
# the second rejected by the database. The whole transaction rolled back and the
# buyer received nothing at all — not one agent of the two, nothing.
#
# It cost a real ₦148,000 order to find, and the confirmation page made it look
# like progress: it re-attempts provisioning on every poll, so it sat on
# "setting up your workspace now" while failing identically each time.


def two_product_order(checkout, storefront, paystack) -> Order:
    order = make_order(checkout, storefront, build=BOTH_PRODUCTS_BUILD)

    return checkout.confirm(
        paystack.charge_from_webhook(
            charge_event(order.paystack_reference, order.amount_minor)
        )
    )


def test_paying_for_two_products_provisions_two_agents(
    db, checkout, storefront, paystack
):
    """The whole of BUG 4, in the smallest form that shows it.

    Asserting on the count and the roles rather than on ``created``, because a
    provision that half-worked would still report success on the first profile.
    """
    order = two_product_order(checkout, storefront, paystack)

    result = ProvisioningService(db).provision(order)

    assert result.created is True
    assert len(result.profiles) == 2
    assert {profile.role for profile in result.profiles} == {
        ROLE_SALES_AGENT,
        ROLE_SUPPORT_AGENT,
    }


def test_both_agents_are_ready_and_usable(db, checkout, storefront, paystack):
    """Two rows is not delivery. Two *working* agents is.

    Each needs its own key and widget token — they are separate installs on
    separate surfaces — and a shared one would make one of the two wrong.
    """
    order = two_product_order(checkout, storefront, paystack)

    result = ProvisioningService(db).provision(order)

    for profile in result.profiles:
        assert profile.status == PROVISION_READY
        assert profile.api_key_hash
        assert profile.widget_token

    tokens = {profile.widget_token for profile in result.profiles}
    assert len(tokens) == 2


def test_two_agents_share_one_workspace_and_one_login(
    db, checkout, storefront, paystack
):
    """They bought two agents, not two companies.

    The reason the constraint could not simply be dropped: one organization and
    one login is the intended shape, and the fix has to keep it while allowing
    two profiles inside it.
    """
    order = two_product_order(checkout, storefront, paystack)

    result = ProvisioningService(db).provision(order)

    organizations = {profile.organization_id for profile in result.profiles}
    assert len(organizations) == 1

    logins = db.query(User).filter(User.email == order.buyer_email).count()
    assert logins == 1


def test_provisioning_two_products_twice_still_delivers_two(
    db, checkout, storefront, paystack
):
    """Idempotency at the new shape.

    The status page polls repeatedly, so this path runs many times for one
    purchase. It must not add a third profile, and it must not lose one.
    """
    order = two_product_order(checkout, storefront, paystack)
    service = ProvisioningService(db)

    first = service.provision(order)
    second = service.provision(order)

    assert second.created is False
    assert len(second.profiles) == 2
    assert {p.id for p in second.profiles} == {p.id for p in first.profiles}
    assert db.query(WorkspaceProfile).count() == 2


def test_one_workspace_cannot_hold_two_of_the_same_agent(
    db, checkout, storefront, paystack
):
    """What the unique constraint is actually for, kept.

    Replacing it with a pair rather than deleting it means a retried or
    duplicated provision still cannot hand a customer two sales reps in one
    workspace — which would double-bill on renewal and leave two greetings
    competing for the same buyers.
    """
    order = two_product_order(checkout, storefront, paystack)
    result = ProvisioningService(db).provision(order)

    sales = next(
        profile
        for profile in result.profiles
        if profile.role == ROLE_SALES_AGENT
    )

    duplicate = WorkspaceProfile(
        organization_id=sales.organization_id,
        order_id=order.id,
        plan_code=sales.plan_code,
        role=ROLE_SALES_AGENT,
        agent_name="Impostor",
        company_name=sales.company_name,
        greeting="hello",
    )
    db.add(duplicate)

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()


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

    other = SUPPORT_BUILD
    second = make_order(checkout, storefront, build=other)
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


@pytest.fixture
def no_paystack_key(monkeypatch):
    """A deployment with payments switched off, stated rather than inherited.

    These tests used to read whatever ``PAYSTACK_SECRET_KEY`` the developer's
    ``.env`` happened to hold, so they passed on a machine with no keys and
    failed on one with them — a suite result that depends on the environment is
    a suite that cannot be trusted about the thing it claims to check. The
    moment a real test key was added locally, three tests went red while the
    code they cover was untouched and correct.
    """
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "", raising=False)
    assert not settings.payments_enabled


def test_checkout_config_reports_disabled_when_no_key_is_set(client, no_paystack_key):
    body = client.get("/api/v1/checkout/config").json()

    assert body["enabled"] is False
    assert body["live_mode"] is False


def test_creating_an_order_without_keys_returns_503_not_500(
    client, storefront, quoted, no_paystack_key
):
    response = client.post(
        "/api/v1/checkout/orders",
        json={"quote_reference": quoted, "email": "buyer@example.com"},
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
    # Read off the order, not looked up in a catalog. A quote-backed order has
    # no catalog plan to look up, and the order is the record of what was sold.
    assert body["order"]["display_amount"] == SALES_QUOTE.display_total
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


# ---------- closing from inside a conversation ----------


@pytest.fixture
def thread(client, storefront) -> str:
    return client.post("/api/v1/sales/conversations").json()["token"]


# The four answers that complete an intake, in the order the agent asks for
# them. Matched to SALES_BUILD, so the figure the conversation reaches is
# SALES_QUOTE and a test can assert on it without hardcoding a number.
INTAKE_ANSWERS = (
    "I need an AI sales representative",
    "just my website",
    "about 2,000 a month",
    "none",
)


def reach_buy_intent(client, thread) -> dict:
    """Talk the agent all the way to a price, the way a buyer does.

    There are no tiers to name any more, so this walks the real intake: four
    answers, then the agent quotes. What it leaves behind is a stored quote and
    ``quote_<reference>`` on the conversation — which is exactly the state the
    widget's close then has to work from.
    """
    for answer in INTAKE_ANSWERS:
        client.post(
            f"/api/v1/sales/conversations/{thread}/messages",
            json={"body": answer},
        )

    return client.get(f"/api/v1/sales/conversations/{thread}").json()


def test_conversation_reaches_a_computed_price_and_remembers_the_quote(client, thread):
    body = reach_buy_intent(client, thread)

    assert body["stage"] == "ready_to_buy"

    # Not a plan code — a reference to the requirement that was priced.
    code = body["interested_plan_code"]
    assert code.startswith("quote_")
    assert find_plan(code) is None

    # And the figure the buyer was actually shown is the computed one.
    messages = client.get(
        f"/api/v1/sales/conversations/{thread}"
    ).json()["messages"]
    assert any(SALES_QUOTE.display_total in m["body"] for m in messages)


def test_checkout_without_a_chosen_plan_is_refused(client, thread):
    response = client.post(
        f"/api/v1/sales/conversations/{thread}/checkout",
        json={"email": "buyer@example.com"},
    )

    assert response.status_code == 400
    assert "plan" in response.json()["detail"].lower()


def test_checkout_without_an_email_is_refused(client, thread):
    reach_buy_intent(client, thread)

    response = client.post(
        f"/api/v1/sales/conversations/{thread}/checkout",
        json={},
    )

    assert response.status_code == 400
    assert "email" in response.json()["detail"].lower()


def test_checkout_on_an_unknown_thread_is_404(client, storefront, quoted):
    response = client.post(
        "/api/v1/sales/conversations/not-a-real-token/checkout",
        json={"email": "buyer@example.com", "quote_reference": quoted},
    )

    assert response.status_code == 404


def test_conversation_checkout_charges_the_computed_price(
    client, db, thread, storefront, monkeypatch, transport
):
    """The widget's own close, end to end, on a quoted build.

    This is the case that broke when the tiers went: the widget sends no plan,
    the route falls back to ``interested_plan_code``, and that is now
    ``quote_<reference>`` rather than a code any plan list contains. If the
    unwrap in ``checkout_from_conversation`` regresses, this 400s.
    """
    reach_buy_intent(client, thread)

    monkeypatch.setattr(
        "app.api.v1.routes.sales.CheckoutService",
        lambda session: CheckoutService(
            session, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
        ),
    )

    response = client.post(
        f"/api/v1/sales/conversations/{thread}/checkout",
        json={"email": "buyer@example.com", "name": "Ada", "company": "Buyer Co"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["amount_minor"] == SALES_QUOTE.total_minor
    assert transport.initialize_calls[-1]["body"]["amount"] == SALES_QUOTE.total_minor


def test_conversation_checkout_ignores_an_amount_in_the_request_body(
    client, db, thread, storefront, monkeypatch, transport
):
    """There is no amount field, so sending one must change nothing."""
    reach_buy_intent(client, thread)

    monkeypatch.setattr(
        "app.api.v1.routes.sales.CheckoutService",
        lambda session: CheckoutService(
            session, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
        ),
    )

    body = client.post(
        f"/api/v1/sales/conversations/{thread}/checkout",
        json={
            "email": "buyer@example.com",
            "amount_minor": 1,
            "amount": 1,
            "price": 1,
        },
    ).json()

    assert body["amount_minor"] == SALES_QUOTE.total_minor


def test_conversation_checkout_refuses_a_plan_that_does_not_exist(
    client, db, thread, storefront, monkeypatch, transport
):
    reach_buy_intent(client, thread)

    monkeypatch.setattr(
        "app.api.v1.routes.sales.CheckoutService",
        lambda session: CheckoutService(
            session, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
        ),
    )

    response = client.post(
        f"/api/v1/sales/conversations/{thread}/checkout",
        json={"email": "buyer@example.com", "plan_code": "free_forever"},
    )

    assert response.status_code == 400


def test_conversation_checkout_without_keys_returns_503(client, thread, no_paystack_key):
    reach_buy_intent(client, thread)

    response = client.post(
        f"/api/v1/sales/conversations/{thread}/checkout",
        json={"email": "buyer@example.com"},
    )

    assert response.status_code == 503


# ---------- buying both products, on the web ----------
#
# The two-product build is the newest thing the engine can price, and the widget
# is where it was least proven: every web checkout test above orders a single
# product. These walk the path a paying customer walks — the intake, the price
# endpoint the buy panel reads, then the order — because the parts were each
# tested and the joins between them were not.

BOTH_PRODUCTS_ANSWERS = (
    "both",
    "my website and whatsapp",
    "about 2,000 a month",
    "none",
)

BOTH_PRODUCTS_BUILD = Requirement(
    products=(PRODUCT_SALES_AGENT, PRODUCT_SUPPORT_AGENT),
    channels=(CHANNEL_WEB, CHANNEL_WHATSAPP),
    monthly_conversations=2_000,
)


def reach_a_two_product_price(client, thread) -> dict:
    for answer in BOTH_PRODUCTS_ANSWERS:
        client.post(
            f"/api/v1/sales/conversations/{thread}/messages",
            json={"body": answer},
        )

    return client.get(f"/api/v1/sales/conversations/{thread}").json()


def test_a_web_buyer_can_pay_for_both_products_at_once(
    client, db, thread, storefront, monkeypatch, transport
):
    """Two products, one payment, and the amount Paystack is asked for is the
    engine's own total — computed here rather than written down, so a pricing
    change cannot leave this asserting a figure we no longer charge.
    """
    expected = price(BOTH_PRODUCTS_BUILD)

    body = reach_a_two_product_price(client, thread)
    assert body["stage"] == "ready_to_buy"

    monkeypatch.setattr(
        "app.api.v1.routes.sales.CheckoutService",
        lambda session: CheckoutService(
            session, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
        ),
    )

    response = client.post(
        f"/api/v1/sales/conversations/{thread}/checkout",
        json={"email": "buyer@brightfoods.example", "name": "Ada Nwosu"},
    )

    assert response.status_code == 201
    order = response.json()

    assert order["amount_minor"] == expected.total_minor
    assert transport.requests[-1]["body"]["amount"] == expected.total_minor

    # And more than either product alone on the same channels and volume, which
    # is the only thing that makes "they bought both" observable in the amount.
    one_only = price(
        Requirement(
            products=(PRODUCT_SALES_AGENT,),
            channels=(CHANNEL_WEB, CHANNEL_WHATSAPP),
            monthly_conversations=2_000,
        )
    )

    assert order["amount_minor"] > one_only.total_minor


def test_the_buy_panel_can_read_the_price_of_a_two_product_quote(
    client, thread, storefront
):
    """What the buy panel fetches before it shows a figure.

    ``chat.js`` unwraps ``quote_<reference>`` and GETs the quote to fill the
    price in, unauthenticated — a buyer holds a conversation token, not a login.
    If this needed auth the panel would show a form with no price; if it named
    one product against two products' total, the buyer would only find out which
    they were buying on Paystack's own page.
    """
    expected = price(BOTH_PRODUCTS_BUILD)

    body = reach_a_two_product_price(client, thread)
    reference = body["interested_plan_code"].removeprefix("quote_")

    response = client.get(f"/api/v1/pricing/quotes/{reference}")

    assert response.status_code == 200
    quote = response.json()

    assert quote["display_total"] == expected.display_total
    assert quote["billing_period"]

    # Both products named, so the price is not attributed to only one of them.
    assert "Sales" in quote["product_name"]
    assert "Support" in quote["product_name"]
