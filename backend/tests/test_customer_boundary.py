"""Test customer boundary security and product model integrity.

Verifies:
1. Public visitor API never leaks internal AI reasoning, rules, signals or chain-of-thought,
   even when an attacker or unauthorized user passes client-controlled debug headers.
2. Only cryptographically verified admin sessions or internal secrets can access reasoning.
3. Complex, malformed, and unclosed thinking tags and prompt leaks are sanitized.
4. Standalone Sales Agent, Standalone Support Agent, and Workforce Bundle produce
   distinct authoritative quotes and persist correctly into Paystack checkout orders.
5. Checkout validates quote references server-side and rejects invalid or fabricated quotes.
"""

import pytest
from jose import jwt
from app.config.settings import settings
from app.models.organization import Organization
from app.models.user import User
from app.schemas.sales import sanitize_customer_body


@pytest.fixture
def storefront(db) -> Organization:
    """The storefront organization matching settings."""
    org = Organization(
        name="NekoSalesAI Demo",
        slug=settings.STOREFRONT_ORG_SLUG,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_sanitize_customer_body():
    """Verify that chain-of-thought, thinking tags, and reasoning blocks are stripped."""
    raw_1 = "<think>The customer seems hesitant about price. I should quote.</think>Hello! Here is your quote."
    assert sanitize_customer_body(raw_1) == "Hello! Here is your quote."

    raw_2 = "[think]Internal step: verifying catalog[/think]We support Web and Telegram."
    assert sanitize_customer_body(raw_2) == "We support Web and Telegram."

    raw_3 = "<reasoning>Rule: discount_requested; Action: escalate</reasoning>I cannot offer discounts directly."
    assert sanitize_customer_body(raw_3) == "I cannot offer discounts directly."

    # Complex / malformed tags
    raw_unclosed = "Hello customer! <think>internal thoughts that got cut off due to max tokens"
    assert sanitize_customer_body(raw_unclosed) == "Hello customer!"

    raw_thought = "<thought>evaluate options</thought>Here are the available plans."
    assert sanitize_customer_body(raw_thought) == "Here are the available plans."

    raw_scratchpad = "[scratchpad]internal notes[/scratchpad]Deployment takes 10 minutes."
    assert sanitize_customer_body(raw_scratchpad) == "Deployment takes 10 minutes."

    raw_untagged = "Internal Reasoning: Evaluating user intent.\nWe are pleased to assist you."
    assert sanitize_customer_body(raw_untagged) == "We are pleased to assist you."

    clean = "Welcome to Nera! How can we help your business?"
    assert sanitize_customer_body(clean) == clean


def test_public_visitor_messages_do_not_leak_reasoning(client, storefront, db):
    """Ensure normal browser/visitor calls receive NO reasoning object or rule citations."""
    # 1. Start a conversation without headers
    resp = client.post("/api/v1/sales/conversations")
    assert resp.status_code == 201
    data = resp.json()
    token = data["token"]

    # Initial greeting in public response must NOT have reasoning
    assert len(data["messages"]) > 0
    assert data["messages"][0]["reasoning"] is None

    # 2. Send a message without debug header
    msg_resp = client.post(
        f"/api/v1/sales/conversations/{token}/messages",
        json={"body": "Hello, how much does the sales agent cost?"},
    )
    assert msg_resp.status_code == 201
    msg_data = msg_resp.json()

    # The public message response must have reasoning=None
    assert msg_data["reasoning"] is None
    assert len(msg_data["body"]) > 0
    assert "<think>" not in msg_data["body"].lower()

    # 3. Read conversation back through GET /conversations/{token}
    get_resp = client.get(f"/api/v1/sales/conversations/{token}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    for m in get_data["messages"]:
        assert m["reasoning"] is None


def test_unauthorized_header_cannot_bypass_reasoning_boundary(client, storefront, db):
    """Prove that passing 'X-Nera-Debug-Reasoning: true' alone FAILS to obtain internal reasoning.

    The boundary strictly checks server-side admin authentication.
    """
    # 1. Start conversation with debug header but NO auth
    resp = client.post(
        "/api/v1/sales/conversations",
        headers={"X-Nera-Debug-Reasoning": "true"},
    )
    assert resp.status_code == 201
    data = resp.json()
    token = data["token"]
    # Reasoning MUST be None!
    assert data["messages"][0]["reasoning"] is None

    # 2. Send visitor message with debug header but NO auth
    msg_resp = client.post(
        f"/api/v1/sales/conversations/{token}/messages",
        json={"body": "What are your business hours?"},
        headers={"X-Nera-Debug-Reasoning": "true"},
    )
    assert msg_resp.status_code == 201
    assert msg_resp.json()["reasoning"] is None

    # 3. Authenticate as a normal customer (is_admin=False)
    normal_user = User(
        full_name="Regular Customer",
        email="customer@example.com",
        password_hash="fakehash",
        is_active=True,
        is_admin=False,
    )
    db.add(normal_user)
    db.commit()
    db.refresh(normal_user)

    customer_token = jwt.encode(
        {"sub": str(normal_user.id)},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    customer_headers = {
        "Authorization": f"Bearer {customer_token}",
        "X-Nera-Debug-Reasoning": "true",
    }

    # Normal customer also receives reasoning: None!
    cust_resp = client.post(
        f"/api/v1/sales/conversations/{token}/messages",
        json={"body": "Tell me more"},
        headers=customer_headers,
    )
    assert cust_resp.status_code == 201
    assert cust_resp.json()["reasoning"] is None

    # 4. Now authenticate as an actual Administrator (is_admin=True)
    admin_user = User(
        full_name="Super Admin",
        email="admin@example.com",
        password_hash="fakehash",
        is_active=True,
        is_admin=True,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    admin_token = jwt.encode(
        {"sub": str(admin_user.id)},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_token}",
        "X-Nera-Debug-Reasoning": "true",
    }

    admin_resp = client.post(
        f"/api/v1/sales/conversations/{token}/messages",
        json={"body": "Admin query checking reasoning rules"},
        headers=admin_headers,
    )
    assert admin_resp.status_code == 201
    # Authorized administrator DOES receive verified reasoning trail
    assert admin_resp.json()["reasoning"] is not None
    assert admin_resp.json()["reasoning"]["rule"]


def test_product_switching_pricing_and_quote_integrity(client, storefront, db):
    """Verify that switching between Sales, Support, and Workforce produces distinct,

    authoritative quotes and does NOT silently default to Sales Agent.
    """
    # 1. AI Sales Agent quote
    sales_resp = client.post(
        "/api/v1/pricing/quote",
        json={"product_type": "sales_agent", "channels": ["web"]},
    )
    assert sales_resp.status_code == 200
    sales_data = sales_resp.json()
    assert sales_data["product_type"] == "sales_agent"
    assert sales_data["product_name"] == "AI Sales Agent"
    assert sales_data["total_minor"] == 199_000_00 + 2_500_00  # base + 500 volume
    assert sales_data["display_total"] == "₦201,500"

    # 2. AI Support Agent quote
    support_resp = client.post(
        "/api/v1/pricing/quote",
        json={"product_type": "support_agent", "channels": ["web"]},
    )
    assert support_resp.status_code == 200
    support_data = support_resp.json()
    assert support_data["product_type"] == "support_agent"
    assert support_data["product_name"] == "AI Support Agent"
    assert support_data["total_minor"] == 149_000_00 + 2_500_00  # base + 500 volume
    assert support_data["display_total"] == "₦151,500"
    # Prove price changed and is NOT sales agent price
    assert support_data["total_minor"] != sales_data["total_minor"]

    # 3. AI Workforce bundle quote
    workforce_resp = client.post(
        "/api/v1/pricing/quote",
        json={"product_type": "workforce_agent", "channels": ["web"]},
    )
    assert workforce_resp.status_code == 200
    workforce_data = workforce_resp.json()
    assert workforce_data["product_type"] == "workforce_agent"
    assert workforce_data["product_name"] == "Workforce"
    assert workforce_data["total_minor"] == 348_000_00 + 2_500_00  # base + 500 volume
    assert workforce_data["display_total"] == "₦350,500"
    # Prove price changed and is NOT sales agent price
    assert workforce_data["total_minor"] != sales_data["total_minor"]
    assert workforce_data["total_minor"] != support_data["total_minor"]

    # 4. Verify alias product_code also works
    support_alias_resp = client.post(
        "/api/v1/pricing/quote",
        json={"product_code": "support_agent", "channels": ["web"]},
    )
    assert support_alias_resp.status_code == 200
    assert support_alias_resp.json()["product_type"] == "support_agent"
    assert support_alias_resp.json()["total_minor"] == 151_500_00


def test_checkout_preserves_selected_product_from_quote(client, storefront, db):
    """Verify that raising a checkout order with a Support Agent quote reference

    correctly generates an order for Support Agent, not Sales Agent.
    """
    # 1. Create a Support Agent quote
    support_quote_resp = client.post(
        "/api/v1/pricing/quote",
        json={"product_type": "support_agent", "channels": ["web", "telegram"]},
    )
    assert support_quote_resp.status_code == 200
    support_quote = support_quote_resp.json()
    quote_ref = support_quote["reference"]

    # 2. Create order using this quote reference
    order_resp = client.post(
        "/api/v1/checkout/orders",
        json={
            "email": "customer@business.ng",
            "name": "Ifeanyi Nnamdi",
            "company": "Nnamdi Logistics Ltd",
            "quote_reference": quote_ref,
        },
    )
    assert order_resp.status_code == 201
    order_data = order_resp.json()

    assert order_data["status"] == "pending"
    assert order_data["plan_name"] == "AI Support Agent"
    assert order_data["amount_minor"] == support_quote["total_minor"]
    assert order_data["display_amount"] == support_quote["display_total"]
    assert "https://checkout.paystack.com/" in order_data["checkout_url"]


def test_checkout_rejects_nonexistent_or_manipulated_quote(client, storefront, db):
    """Verify that checkout strictly validates quote existence and rejects fake references."""
    order_resp = client.post(
        "/api/v1/checkout/orders",
        json={
            "email": "attacker@fake.ng",
            "quote_reference": "Q-NON-EXISTENT-FAKE-123",
        },
    )
    # Backend rejects non-existent quote with 400 Bad Request
    assert order_resp.status_code == 400
    assert "there is no quote" in order_resp.json()["detail"].lower()
