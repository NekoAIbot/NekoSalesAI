"""Quotes: issuing, redeeming, and refusing to be told a price.

The property under test throughout is that a quote reference is a *name for a
requirement*, not a bearer token for an amount. Most tests here are a version of
"the row said one thing, the engine says another, and the engine wins".
"""

import json

import pytest
from sqlalchemy import func, select

from app.models.quote import Quote
from app.payments import PaystackClient
from app.payments.checkout import CheckoutError, CheckoutService
from app.pricing.complexity import PricingError, Requirement, price
from app.pricing.quotes import QuoteError, QuoteService
from tests.test_checkout import TEST_SECRET, FakeTransport


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def checkout(db, transport) -> CheckoutService:
    return CheckoutService(
        db, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
    )


def _requirement(**overrides) -> Requirement:
    params = {
        "product_type": "sales_agent",
        "channels": ("web", "telegram"),
        "integrations": ("calendar",),
        "languages": (),
        "monthly_conversations": 2_000,
        "workflow_steps": 0,
    }
    params.update(overrides)
    return Requirement(**params)


# ---------- issuing ----------


def test_issue_stores_the_requirement_and_its_computed_total(db):
    requirement = _requirement()
    quote = QuoteService(db).issue(requirement)

    assert quote.reference.startswith("qt_")
    assert quote.total_minor == price(requirement).total_minor
    assert quote.product_type == "sales_agent"

    stored = json.loads(quote.requirement_json)
    assert stored["channels"] == ["web", "telegram"]
    assert stored["monthly_conversations"] == 2_000


def test_each_quote_gets_its_own_unguessable_reference(db):
    service = QuoteService(db)
    first = service.issue(_requirement())
    second = service.issue(_requirement())

    assert first.reference != second.reference
    # 12 random bytes as hex, plus the "qt_" prefix.
    assert len(first.reference) == 27


def test_issue_refuses_a_requirement_the_engine_will_not_price(db):
    with pytest.raises(PricingError):
        QuoteService(db).issue(_requirement(channels=("fax",)))

    assert db.execute(select(func.count()).select_from(Quote)).scalar_one() == 0


# ---------- redeeming ----------


def test_redeem_returns_a_plan_priced_by_the_engine(db):
    requirement = _requirement()
    quote = QuoteService(db).issue(requirement)

    redeemed, plan = QuoteService(db).redeem(quote.reference)

    assert redeemed.id == quote.id
    assert plan.amount_minor == price(requirement).total_minor
    assert plan.currency == "NGN"
    assert plan.code == f"quote_{quote.reference}"


def test_redeem_refuses_an_unknown_reference(db):
    with pytest.raises(QuoteError):
        QuoteService(db).redeem("qt_deadbeefdeadbeefdeadbeef")


def test_a_tampered_total_is_refused_not_charged(db):
    """The whole reason the requirement is stored instead of just the figure."""
    quote = QuoteService(db).issue(_requirement())

    quote.total_minor = 100  # ₦1 for an AI product
    db.commit()

    with pytest.raises(QuoteError):
        QuoteService(db).redeem(quote.reference)


def test_an_unreadable_requirement_is_refused_not_guessed(db):
    quote = QuoteService(db).issue(_requirement())

    quote.requirement_json = "{not json at all"
    db.commit()

    with pytest.raises(QuoteError):
        QuoteService(db).redeem(quote.reference)


def test_a_requirement_edited_to_something_cheaper_is_refused(db):
    """Editing the requirement changes what it re-prices at, which no longer
    matches the total we recorded — so the mismatch check catches it."""
    quote = QuoteService(db).issue(_requirement())

    quote.requirement_json = json.dumps(
        {
            "product_type": "sales_agent",
            "channels": ["web"],
            "integrations": [],
            "languages": [],
            "monthly_conversations": 0,
            "workflow_steps": 0,
            "discount_percent": 0,
        }
    )
    db.commit()

    with pytest.raises(QuoteError):
        QuoteService(db).redeem(quote.reference)


def test_a_requirement_edited_to_grant_a_discount_is_refused(db):
    quote = QuoteService(db).issue(_requirement())

    stored = json.loads(quote.requirement_json)
    stored["discount_percent"] = 90
    quote.requirement_json = json.dumps(stored)
    db.commit()

    with pytest.raises(QuoteError):
        QuoteService(db).redeem(quote.reference)


def test_a_requirement_we_no_longer_build_is_refused(db):
    quote = QuoteService(db).issue(_requirement())

    stored = json.loads(quote.requirement_json)
    stored["product_type"] = "mind_reader"
    quote.requirement_json = json.dumps(stored)
    db.commit()

    with pytest.raises(QuoteError):
        QuoteService(db).redeem(quote.reference)


# ---------- the checkout ----------


def test_checkout_charges_the_recomputed_quote_total(
    db, organization, checkout, transport
):
    requirement = _requirement()
    quote = QuoteService(db).issue(requirement)

    order = checkout.create_order(
        organization_id=organization.id,
        quote_reference=quote.reference,
        buyer_email="buyer@example.com",
    )

    expected = price(requirement).total_minor
    assert order.amount_minor == expected
    assert order.currency == "NGN"

    # And the same figure is what actually crossed the wire.
    assert transport.initialize_calls[-1]["body"]["amount"] == expected


def test_checkout_refuses_an_unknown_quote_reference(organization, checkout):
    with pytest.raises(CheckoutError):
        checkout.create_order(
            organization_id=organization.id,
            quote_reference="qt_000000000000000000000000",
            buyer_email="buyer@example.com",
        )


def test_checkout_refuses_a_tampered_quote(db, organization, checkout, transport):
    quote = QuoteService(db).issue(_requirement())
    quote.total_minor = 100
    db.commit()

    with pytest.raises(CheckoutError):
        checkout.create_order(
            organization_id=organization.id,
            quote_reference=quote.reference,
            buyer_email="buyer@example.com",
        )

    # Nothing reached the payment provider.
    assert transport.initialize_calls == []


def test_checkout_requires_one_identifier_not_both(db, organization, checkout):
    """Two identifiers would mean picking one, and whichever rule we picked
    would be a discount the buyer chose."""
    quote = QuoteService(db).issue(_requirement())

    with pytest.raises(CheckoutError):
        checkout.create_order(
            organization_id=organization.id,
            plan_code="starter_monthly",
            quote_reference=quote.reference,
            buyer_email="buyer@example.com",
        )


def test_checkout_requires_at_least_one_identifier(organization, checkout):
    with pytest.raises(CheckoutError):
        checkout.create_order(
            organization_id=organization.id,
            buyer_email="buyer@example.com",
        )


# ---------- over HTTP ----------


def test_quote_endpoint_returns_a_redeemable_reference(client, db):
    response = client.post(
        "/api/v1/pricing/quote",
        json={
            "product_type": "sales_agent",
            "channels": ["web", "whatsapp"],
            "monthly_conversations": 2000,
        },
    )

    assert response.status_code == 200
    body = response.json()
    reference = body["reference"]
    assert reference.startswith("qt_")

    stored = db.execute(
        select(Quote).where(Quote.reference == reference)
    ).scalars().first()
    assert stored is not None
    assert stored.total_minor == body["total_minor"]

    _, plan = QuoteService(db).redeem(reference)
    assert plan.amount_minor == body["total_minor"]


def test_a_refused_requirement_stores_no_quote(client, db):
    response = client.post(
        "/api/v1/pricing/quote",
        json={"product_type": "sales_agent", "channels": ["fax"]},
    )

    assert response.status_code == 400
    assert db.execute(select(func.count()).select_from(Quote)).scalar_one() == 0


# ---------- quote to paid order, end to end ----------


@pytest.fixture
def storefront(db):
    from app.config.settings import settings
    from app.models.organization import Organization

    org = Organization(name="NekoSalesAI Demo", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_a_quoted_price_can_be_bought_at_exactly_that_price(
    client, db, storefront, monkeypatch
):
    """The path the factory actually sells through: describe what you want,
    get a price, buy it. The figure must survive unchanged from quote to the
    amount the payment provider is asked for."""
    transport = FakeTransport()
    monkeypatch.setattr(
        "app.payments.checkout.PaystackClient",
        lambda *a, **kw: PaystackClient(secret_key=TEST_SECRET, transport=transport),
    )

    quoted = client.post(
        "/api/v1/pricing/quote",
        json={
            "product_type": "sales_agent",
            "channels": ["web", "telegram"],
            "integrations": ["calendar"],
            "monthly_conversations": 2000,
        },
    ).json()

    order = client.post(
        "/api/v1/checkout/orders",
        json={
            "quote_reference": quoted["reference"],
            "email": "buyer@example.com",
        },
    )

    assert order.status_code == 201
    body = order.json()
    assert body["amount_minor"] == quoted["total_minor"]
    assert transport.initialize_calls[-1]["body"]["amount"] == quoted["total_minor"]


def test_the_checkout_endpoint_still_refuses_to_be_told_an_amount(
    client, db, storefront, monkeypatch
):
    transport = FakeTransport()
    monkeypatch.setattr(
        "app.payments.checkout.PaystackClient",
        lambda *a, **kw: PaystackClient(secret_key=TEST_SECRET, transport=transport),
    )

    quote = QuoteService(db).issue(_requirement())

    response = client.post(
        "/api/v1/checkout/orders",
        json={
            "quote_reference": quote.reference,
            "email": "buyer@example.com",
            "amount_minor": 100,
            "total_minor": 100,
            "price": 1,
        },
    )

    assert response.status_code == 201
    assert response.json()["amount_minor"] == price(_requirement()).total_minor

