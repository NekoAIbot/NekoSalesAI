"""Zuri rename, entitlements gating, and customer agent naming."""

from datetime import datetime, timezone

import pytest

from app.mira import coordinator
from app.mira.entitlements import for_organization
from app.models.order import ORDER_PAID, ORDER_PENDING, Order
from app.models.organization import Organization
from app.models.workspace_profile import WorkspaceProfile
from app.products.config import ROLE_SALES_AGENT, ROLE_SUPPORT_AGENT


def test_zuri_help_identifies_as_zuri(db, organization):
    reply = coordinator.respond(db, organization.id, "/help", command="help")
    assert "i'm zuri" in reply.lower()
    assert "nera business manager" in reply.lower()
    assert "mira" not in reply.lower()


def test_entitlements_reflect_purchases(db, organization):
    # Empty org: no entitlements
    ent = for_organization(db, organization.id)
    assert not ent.has_any_purchase
    assert not ent.has_sales
    assert not ent.has_support
    assert not ent.has_workforce

    # Add a paid sales order
    order = Order(
        organization_id=organization.id,
        plan_code="sales_agent",
        plan_name="AI Sales Agent",
        billing_period="monthly",
        amount_minor=199_000_00,
        currency="NGN",
        buyer_email="buyer@example.com",
        status=ORDER_PAID,
        paystack_reference="ref_sales",
        paid_at=datetime.now(timezone.utc),
    )
    db.add(order)
    db.commit()

    ent = for_organization(db, organization.id)
    assert ent.has_any_purchase
    assert ent.has_sales
    assert not ent.has_support
    assert not ent.has_workforce

    # Help text surfaces what's active and what's locked
    help_text = coordinator.respond(db, organization.id, "/help", command="help")
    assert "sales: i watch your paid orders" in help_text
    assert "buy the other agent" in help_text


def test_rename_purchased_agent(client, db, auth_headers):
    # Find the test user's org
    from app.models.user import User

    user = db.query(User).filter_by(email="founder@nekosales.ai").first()
    org_id = user.organization_id

    # Seed a provisioned profile
    profile = WorkspaceProfile(
        organization_id=org_id,
        plan_code="sales_agent",
        role=ROLE_SALES_AGENT,
        agent_name="Ada",
        company_name="Acme",
        greeting="Hi, I'm Ada. I'm the sales agent for Acme.",
    )
    db.add(profile)
    db.commit()

    # Rename it through the new endpoint
    response = client.patch(
        f"/api/v1/product-config/agents/{ROLE_SALES_AGENT}/name",
        json={"name": "Chidi"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_name"] == "Chidi"

    # Profile row was updated
    db.refresh(profile)
    assert profile.agent_name == "Chidi"
    assert "Chidi" in profile.greeting


def test_rename_rejects_empty_name(client, db, auth_headers):
    response = client.patch(
        f"/api/v1/product-config/agents/{ROLE_SALES_AGENT}/name",
        json={"name": "   "},
        headers=auth_headers,
    )
    assert response.status_code == 422
