"""The storefront offers both products, and the builder can actually buy them.

Stage D made a support agent priceable and provisionable; nothing on the
landing page offered one, so no customer could buy the product. These tests
cover that gap and the ones it opens.

The property worth pinning hardest: the *page* never carries a computed price.
The fixed tiers render theirs because they are published figures in reviewable
Python. A built product's price exists only in a server response, so a template
that rendered one would be a second place a figure could come from.
"""

import re

import pytest

from app.config.settings import settings
from app.models.organization import Organization
from app.payments import PaystackClient
from app.pricing.complexity import (
    CHANNEL_ADD_MINOR,
    PRODUCT_NAMES,
    PRODUCT_SUPPORT_AGENT,
    Requirement,
)
from app.web.routes import _builder_options
from tests.test_checkout import TEST_SECRET, FakeTransport


@pytest.fixture
def storefront(db) -> Organization:
    org = Organization(name="NekoSalesAI Demo", slug=settings.STOREFRONT_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


# ---------- the page offers both products ----------


def test_the_landing_page_offers_every_product_the_factory_prices(client):
    body = client.get("/").text

    for name in PRODUCT_NAMES.values():
        assert name in body, f"{name} is priceable but not offered on the page"


def test_the_builder_offers_the_support_agent_by_code(client):
    body = client.get("/").text

    assert 'value="support_agent"' in body
    assert "AI Support Agent" in body


def test_the_builder_offers_every_channel_the_engine_can_price(client):
    """A form listing a channel the engine refuses would take an order we
    would then have to decline."""
    body = client.get("/").text

    for code in CHANNEL_ADD_MINOR:
        assert f'value="{code}"' in body


def test_the_builder_options_come_from_the_pricing_engine():
    options = _builder_options()

    assert [p["code"] for p in options["products"]] == list(PRODUCT_NAMES)
    assert [c["code"] for c in options["channels"]] == list(CHANNEL_ADD_MINOR)


def test_the_builder_publishes_no_prices(client):
    """The page must not carry a figure for a built product.

    Two figures for one thing is one figure too many: the page's copy would go
    stale the moment the engine's constants moved, and a buyer would have been
    shown a number we no longer charge.
    """
    body = client.get("/").text
    builder = body[body.index('id="build"'):body.index('id="faq"')]

    # No add-on amount from the pricing engine appears in the builder markup.
    for amount_minor in CHANNEL_ADD_MINOR.values():
        if amount_minor == 0:
            continue
        assert f"{amount_minor // 100:,}" not in builder


def test_the_page_still_publishes_the_fixed_tiers(client):
    """The builder is an addition, not a replacement. These are published
    figures and the agent quotes them."""
    from app.catalog import PLANS

    body = client.get("/").text

    for plan in PLANS:
        assert plan.display_price in body


# ---------- buying a support agent, end to end ----------


def test_a_support_agent_can_be_quoted_and_bought(
    client, db, storefront, monkeypatch
):
    """The gap Stage D left, closed: a customer can see and buy this product.

    Deliberately the whole path rather than a unit test of either half. The
    thing that was broken was not a function; it was that no route from a
    visitor to a provisioned support agent existed.
    """
    transport = FakeTransport()
    monkeypatch.setattr(
        "app.payments.checkout.PaystackClient",
        lambda *a, **kw: PaystackClient(secret_key=TEST_SECRET, transport=transport),
    )

    quoted = client.post(
        "/api/v1/pricing/quote",
        json={
            "product_type": "support_agent",
            "channels": ["web", "whatsapp"],
            "monthly_conversations": 2000,
        },
    )

    assert quoted.status_code == 200
    body = quoted.json()
    assert body["product_type"] == "support_agent"
    assert body["product_name"] == "AI Support Agent"
    assert body["reference"].startswith("qt_")

    order = client.post(
        "/api/v1/checkout/orders",
        json={"quote_reference": body["reference"], "email": "buyer@example.com"},
    )

    assert order.status_code == 201
    assert order.json()["amount_minor"] == body["total_minor"]
    assert transport.initialize_calls[-1]["body"]["amount"] == body["total_minor"]


def test_buying_a_support_agent_provisions_a_support_agent(
    client, db, storefront, monkeypatch
):
    """The product delivered is the product bought — not a sales rep with a
    different name on it."""
    from app.models.order import ORDER_PAID
    from app.payments.provisioning import ProvisioningService
    from app.products.config import ROLE_SUPPORT_AGENT
    from app.pricing.quotes import QuoteService

    quote = QuoteService(db).issue(
        Requirement(product_type=PRODUCT_SUPPORT_AGENT)
    )

    transport = FakeTransport()
    from app.payments.checkout import CheckoutService

    order = CheckoutService(
        db, client=PaystackClient(secret_key=TEST_SECRET, transport=transport)
    ).create_order(
        organization_id=storefront.id,
        quote_reference=quote.reference,
        buyer_email="clinic@example.com",
        buyer_company="Bright Dental",
    )

    order.status = ORDER_PAID
    db.commit()

    result = ProvisioningService(db).provision(order)

    assert result.profile.role == ROLE_SUPPORT_AGENT
    assert "support" in result.profile.greeting.lower()
    assert "sales rep" not in result.profile.greeting.lower()


def test_the_provisioned_support_agent_refuses_to_sell(
    client, db, storefront, monkeypatch
):
    """The end of the whole chain: what the customer's visitors actually get."""
    from app.models.conversation import STAGE_GREETING
    from app.models.order import ORDER_PAID
    from app.payments.checkout import CheckoutService
    from app.payments.provisioning import ProvisioningService
    from app.pricing.quotes import QuoteService
    from app.products.resolver import resolve_config
    from app.sales.agent import RULE_NOT_A_SELLER, compose_reply

    quote = QuoteService(db).issue(
        Requirement(product_type=PRODUCT_SUPPORT_AGENT)
    )

    order = CheckoutService(
        db,
        client=PaystackClient(
            secret_key=TEST_SECRET, transport=FakeTransport()
        ),
    ).create_order(
        organization_id=storefront.id,
        quote_reference=quote.reference,
        buyer_email="clinic@example.com",
        buyer_company="Bright Dental",
    )

    order.status = ORDER_PAID
    db.commit()

    profile = ProvisioningService(db).provision(order).profile

    config = resolve_config(db, profile.organization_id)
    reply = compose_reply("how much does it cost", STAGE_GREETING, config=config)

    assert reply.reasoning.rule == RULE_NOT_A_SELLER
    assert reply.needs_approval is True


# ---------- the checkout still refuses to be priced by its caller ----------


def test_the_builder_path_cannot_name_its_own_price(
    client, db, storefront, monkeypatch
):
    """The builder posts a reference and an email. This asserts that adding an
    amount to that request changes nothing."""
    monkeypatch.setattr(
        "app.payments.checkout.PaystackClient",
        lambda *a, **kw: PaystackClient(
            secret_key=TEST_SECRET, transport=FakeTransport()
        ),
    )

    quoted = client.post(
        "/api/v1/pricing/quote",
        json={"product_type": "support_agent", "channels": ["web"]},
    ).json()

    order = client.post(
        "/api/v1/checkout/orders",
        json={
            "quote_reference": quoted["reference"],
            "email": "buyer@example.com",
            "amount_minor": 100,
            "total_minor": 100,
        },
    )

    assert order.status_code == 201
    assert order.json()["amount_minor"] == quoted["total_minor"]


def test_the_quote_endpoint_is_reachable_without_an_account(client, db):
    """A visitor deciding whether to buy has no account yet."""
    response = client.post(
        "/api/v1/pricing/quote",
        json={"product_type": "support_agent", "channels": ["web"]},
    )

    assert response.status_code == 200


# ---------- the builder script is wired in ----------


def test_the_builder_script_is_loaded(client):
    assert "/static/js/builder.js" in client.get("/").text


def test_the_builder_script_computes_nothing(client):
    """A guard against the obvious future mistake: totalling in the browser.

    If this file could add up a quote it could disagree with the server about
    one, and the buyer would reasonably expect the figure they were shown.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "app" / "web" / "static" / "js" / "builder.js"
    ).read_text()

    # No pricing constant from the engine is duplicated into the client.
    for amount_minor in CHANNEL_ADD_MINOR.values():
        if amount_minor == 0:
            continue
        assert str(amount_minor) not in source
        assert str(amount_minor // 100) not in source

    # And it sends no amount to the checkout.
    assert "amount_minor" not in source
    assert re.search(r"total\s*[+*]", source) is None
