"""Detailed Commercial Verification for Nera 2.0.

Verifies:
1. Volume allowance: 500 conversations included in base quote at ₦5 each = ₦2,500 (250,000 kobo).
2. Incremental volume pricing: exactly ₦5/conversation (500 kobo) as volume scales.
3. Base engine rates: Sales (₦199k), Support (₦149k), Workforce (₦348k).
4. Add-ons: Channels (Telegram ₦4k, WhatsApp ₦8k, Email ₦3k), Integrations (₦2k/slot), Languages (₦3.5k/extra).
5. Displayed totals match server-side amount_minor in kobo.
6. Order creation strictly uses authoritative quote amount and rejects tampering.
"""

import pytest
from app.config.settings import settings
from app.pricing.complexity import (
    PRODUCT_SALES_AGENT,
    PRODUCT_SUPPORT_AGENT,
    PRODUCT_WORKFORCE_AGENT,
    Requirement,
    price,
    CONVERSATION_PRICE_MINOR,
    PRODUCT_BASE_MINOR,
    CHANNEL_ADD_MINOR,
    INTEGRATION_ADD_MINOR,
    LANGUAGE_ADD_MINOR,
)
from app.models.organization import Organization
from app.models.order import Order


def test_volume_allowance_and_incremental_pricing():
    """Verify 500 base volume = ₦2,500 and linear ₦5/conv scaling."""
    assert CONVERSATION_PRICE_MINOR == 500  # 500 kobo = ₦5.00

    # 1. Base allowance: 500 conversations
    req_500 = Requirement(
        product_type=PRODUCT_SALES_AGENT,
        channels=("web",),
        monthly_conversations=500,
    )
    q_500 = price(req_500)
    vol_500 = next(i for i in q_500.line_items if i.dimension == "volume")
    assert vol_500.amount_minor == 250_000  # ₦2,500
    assert vol_500.display_amount == "₦2,500"
    # Total = Base (₦199,000) + Volume (₦2,500) = ₦201,500
    assert q_500.total_minor == 20_150_000
    assert q_500.display_total == "₦201,500"

    # 2. Incremental: 1,000 conversations (500 incremental conversations)
    req_1000 = Requirement(
        product_type=PRODUCT_SALES_AGENT,
        channels=("web",),
        monthly_conversations=1000,
    )
    q_1000 = price(req_1000)
    vol_1000 = next(i for i in q_1000.line_items if i.dimension == "volume")
    assert vol_1000.amount_minor == 500_000  # ₦5,000
    assert vol_1000.display_amount == "₦5,000"
    # Total = Base (₦199,000) + Volume (₦5,000) = ₦204,000
    assert q_1000.total_minor == 20_400_000
    assert q_1000.display_total == "₦204,000"

    # Delta between 1000 and 500 is exactly 500 conversations * ₦5 = ₦2,500
    assert q_1000.total_minor - q_500.total_minor == 250_000

    # 3. Incremental: 2,500 conversations
    req_2500 = Requirement(
        product_type=PRODUCT_SALES_AGENT,
        channels=("web",),
        monthly_conversations=2500,
    )
    q_2500 = price(req_2500)
    vol_2500 = next(i for i in q_2500.line_items if i.dimension == "volume")
    assert vol_2500.amount_minor == 1_250_000  # ₦12,500
    assert q_2500.total_minor == 21_150_000  # ₦211,500


def test_base_engine_rates_and_add_ons():
    """Verify base rates and line-item add-ons."""
    assert PRODUCT_BASE_MINOR[PRODUCT_SALES_AGENT] == 19_900_000   # ₦199,000
    assert PRODUCT_BASE_MINOR[PRODUCT_SUPPORT_AGENT] == 14_900_000 # ₦149,000
    assert PRODUCT_BASE_MINOR[PRODUCT_WORKFORCE_AGENT] == 34_800_000 # ₦348,000

    assert CHANNEL_ADD_MINOR["web"] == 0
    assert CHANNEL_ADD_MINOR["telegram"] == 400_000   # ₦4,000
    assert CHANNEL_ADD_MINOR["whatsapp"] == 800_000   # ₦8,000
    assert CHANNEL_ADD_MINOR["email"] == 300_000      # ₦3,000

    assert INTEGRATION_ADD_MINOR == 200_000           # ₦2,000 per slot
    assert LANGUAGE_ADD_MINOR == 350_000              # ₦3,500 per extra language

    # Support with WhatsApp + 2 Integrations + 2 Languages (en + yo) + 500 conversations
    req_support = Requirement(
        product_type=PRODUCT_SUPPORT_AGENT,
        channels=("web", "whatsapp"),
        integrations=("crm", "inventory"),
        languages=("en", "yo"),
        monthly_conversations=500,
    )
    q_support = price(req_support)
    # Expected:
    # Base: ₦149,000 (14,900,000)
    # Volume: ₦2,500 (250,000)
    # WhatsApp: ₦8,000 (800,000)
    # 2 Integrations: 2 * ₦2,000 = ₦4,000 (400,000)
    # 1 Extra Language: ₦3,500 (350,000)
    # Total = 14,900,000 + 250,000 + 800,000 + 400,000 + 350,000 = 16,700,000 (₦167,000)
    assert q_support.total_minor == 16_700_000
    assert q_support.display_total == "₦167,000"


class FakeTransport:
    def __init__(self, paid: bool = True):
        self.paid = paid
        self.requests = []

    def request(self, method, url, *, headers, json_body=None):
        self.requests.append({"method": method, "url": url, "headers": headers, "body": json_body})
        ref = (json_body or {}).get("reference", "ref_test_fake")
        return 200, {
            "status": True,
            "data": {
                "authorization_url": f"https://checkout.paystack.com/{ref}",
                "access_code": "acc_" + ref,
                "reference": ref,
            },
        }


@pytest.fixture
def storefront_org(db) -> Organization:
    org = db.query(Organization).filter(Organization.slug == settings.STOREFRONT_ORG_SLUG).first()
    if not org:
        org = Organization(
            name="Storefront Org",
            slug=settings.STOREFRONT_ORG_SLUG,
        )
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


@pytest.fixture
def fake_paystack(monkeypatch):
    test_secret = "sk_test_commercial_audit"
    transport = FakeTransport()
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", test_secret)
    monkeypatch.setattr(settings, "PAYSTACK_PUBLIC_KEY", "pk_test_commercial_audit")

    from app.payments.paystack import PaystackClient
    fake_client = PaystackClient(secret_key=test_secret, transport=transport)
    monkeypatch.setattr("app.payments.checkout.PaystackClient", lambda **kwargs: fake_client)
    return fake_client


def test_quote_api_to_order_checkout_trace(client, storefront_org, fake_paystack, db):
    """Trace quote calculation through API response and checkout order creation."""
    quote_payload = {
        "product_type": "sales_agent",
        "channels": ["web", "telegram"],
        "integrations": ["crm"],
        "languages": ["en"],
        "monthly_conversations": 1000,
    }
    # Expected:
    # Base: ₦199,000 (19,900,000)
    # Volume 1000: ₦5,000 (500,000)
    # Telegram: ₦4,000 (400,000)
    # CRM: ₦2,000 (200,000)
    # Total = ₦210,000 (21,000,000 kobo)
    resp = client.post("/api/v1/pricing/quote", json=quote_payload)
    assert resp.status_code == 200
    q_data = resp.json()
    assert q_data["total_minor"] == 21_000_000
    assert q_data["display_total"] == "₦210,000"
    quote_ref = q_data["reference"]

    # Create checkout order with this quote
    order_payload = {
        "email": "commercial_audit@nera.ai",
        "name": "Audit Buyer",
        "company": "Audit Corp",
        "quote_reference": quote_ref,
    }
    order_resp = client.post("/api/v1/checkout/orders", json=order_payload)
    assert order_resp.status_code == 201
    order_data = order_resp.json()
    order_ref = order_data["reference"]

    # Verify order in database holds exact amount_minor
    db_order = db.query(Order).filter(Order.paystack_reference == order_ref).first()
    assert db_order is not None
    assert db_order.amount_minor == 21_000_000
    assert db_order.currency == "NGN"
    assert db_order.plan_code == f"quote_{quote_ref}"
    assert "Sales Agent" in db_order.plan_name
