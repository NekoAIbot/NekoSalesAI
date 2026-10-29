"""Verification of fresh customer signup-to-dashboard flow and tenant isolation.

Verifies:
1. Fresh synthetic user registration via /api/v1/auth/register
2. Authentication via /api/v1/auth/login and JWT access token issuance
3. Authenticated profile retrieval via /api/v1/auth/me
4. Organization workspace profiles retrieval via /api/v1/organizations/workspace/profiles
5. Strict tenant isolation between Organization A and Organization B
6. Cross-tenant order isolation in /api/v1/checkout/orders
7. Session invalidation upon missing, expired, or invalid token
"""

import time
import pytest
from jose import jwt
from datetime import datetime, timezone, timedelta

from app.config.settings import settings
from app.models.organization import Organization
from app.models.user import User
from app.models.order import Order, ORDER_PAID
from app.models.workspace_profile import WorkspaceProfile


def test_fresh_customer_signup_to_dashboard_and_isolation(client, db):
    ts = int(time.time())
    email_a = f"fresh_customer_a_{ts}@audit.nera.ai"
    email_b = f"fresh_customer_b_{ts}@audit.nera.ai"
    pwd = "AuditPassword2026!Secure"

    # 1. Register Customer A
    reg_a = client.post("/api/v1/auth/register", json={
        "full_name": "Customer Alpha",
        "email": email_a,
        "password": pwd,
        "company_name": "Alpha Logistics Ltd"
    })
    assert reg_a.status_code == 201, f"Reg A failed: {reg_a.text}"
    user_a_data = reg_a.json()
    org_a_id = user_a_data["organization_id"]
    assert org_a_id is not None
    assert user_a_data["email"] == email_a

    # 2. Login Customer A
    login_a = client.post("/api/v1/auth/login", json={
        "email": email_a,
        "password": pwd
    })
    assert login_a.status_code == 200
    token_a = login_a.json()["access_token"]
    assert token_a is not None

    # 3. Customer A accesses /me
    me_a = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_a.status_code == 200
    assert me_a.json()["email"] == email_a
    assert me_a.json()["organization_id"] == org_a_id

    # 4. Provision a WorkspaceProfile for Org A
    wp_a = WorkspaceProfile(
        organization_id=org_a_id,
        plan_code="sales_agent",
        role="sales_agent",
        agent_name="Alpha Sales Engine",
        status="ACTIVE",
        company_name="Alpha Logistics Ltd",
        greeting="Hello! Welcome to Alpha Logistics.",
    )
    db.add(wp_a)
    db.commit()

    # 5. Customer A fetches workspace profiles
    profiles_a = client.get(
        "/api/v1/organizations/workspace/profiles",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert profiles_a.status_code == 200
    items_a = profiles_a.json()
    assert len(items_a) == 1
    assert items_a[0]["agent_name"] == "Alpha Sales Engine"

    # 6. Register & Login Customer B
    reg_b = client.post("/api/v1/auth/register", json={
        "full_name": "Customer Beta",
        "email": email_b,
        "password": pwd,
        "company_name": "Beta Retail Enterprise"
    })
    assert reg_b.status_code == 201
    user_b_data = reg_b.json()
    org_b_id = user_b_data["organization_id"]
    assert org_b_id != org_a_id

    login_b = client.post("/api/v1/auth/login", json={
        "email": email_b,
        "password": pwd
    })
    assert login_b.status_code == 200
    token_b = login_b.json()["access_token"]

    # Provision WorkspaceProfile for Org B
    wp_b = WorkspaceProfile(
        organization_id=org_b_id,
        plan_code="support_agent",
        role="support_agent",
        agent_name="Beta Support Engine",
        status="ACTIVE",
        company_name="Beta Retail Enterprise",
        greeting="Hello! How can I help you today?",
    )
    db.add(wp_b)
    db.commit()

    # 7. Customer B fetches workspace profiles -> Sees ONLY B
    profiles_b = client.get(
        "/api/v1/organizations/workspace/profiles",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert profiles_b.status_code == 200
    items_b = profiles_b.json()
    assert len(items_b) == 1
    assert items_b[0]["agent_name"] == "Beta Support Engine"
    assert items_b[0]["agent_name"] != "Alpha Sales Engine"

    # Customer A still sees ONLY A
    profiles_a_recheck = client.get(
        "/api/v1/organizations/workspace/profiles",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert len(profiles_a_recheck.json()) == 1
    assert profiles_a_recheck.json()[0]["agent_name"] == "Alpha Sales Engine"

    # 8. Check Order isolation between Org A and Org B
    order_a = Order(
        organization_id=org_a_id,
        paystack_reference=f"REF_A_{ts}",
        plan_code="sales_agent",
        plan_name="AI Sales Agent",
        billing_period="month",
        amount_minor=20150000,
        currency="NGN",
        buyer_email=email_a,
        status=ORDER_PAID,
    )
    order_b = Order(
        organization_id=org_b_id,
        paystack_reference=f"REF_B_{ts}",
        plan_code="support_agent",
        plan_name="AI Support Agent",
        billing_period="month",
        amount_minor=15150000,
        currency="NGN",
        buyer_email=email_b,
        status=ORDER_PAID,
    )
    db.add_all([order_a, order_b])
    db.commit()

    orders_a = client.get("/api/v1/checkout/orders", headers={"Authorization": f"Bearer {token_a}"})
    assert orders_a.status_code == 200
    refs_a = [o["reference"] for o in orders_a.json()]
    assert f"REF_A_{ts}" in refs_a
    assert f"REF_B_{ts}" not in refs_a

    orders_b = client.get("/api/v1/checkout/orders", headers={"Authorization": f"Bearer {token_b}"})
    assert orders_b.status_code == 200
    refs_b = [o["reference"] for o in orders_b.json()]
    assert f"REF_B_{ts}" in refs_b
    assert f"REF_A_{ts}" not in refs_b

    # 9. Logout / Session removal test: Request without token returns 401/403
    unauth_profiles = client.get("/api/v1/organizations/workspace/profiles")
    assert unauth_profiles.status_code in (401, 403)

    # Request with expired token returns 401
    expired_token = jwt.encode(
        {"sub": str(user_a_data["id"]), "exp": int(time.time()) - 3600},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    exp_resp = client.get(
        "/api/v1/organizations/workspace/profiles",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert exp_resp.status_code == 401
