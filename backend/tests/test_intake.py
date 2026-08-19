"""Product config intake: customer requirements become the agent's script.

The bug these tests exist to prevent: an intake that either fails to govern
the agent (the customer configures their product and the agent keeps saying
something else) or governs the wrong agent (one tenant's form rewriting
another tenant's replies).

Money arrives as a decimal string because that is what a form posts. It must
survive the trip to integer minor units exactly — a price the customer typed
and a price we charge that differ by a kobo is a support ticket.
"""

import json

import pytest

from app.models.organization import Organization
from app.models.user import User
from app.models.workspace_profile import PROVISION_READY, WorkspaceProfile
from app.products.config import (
    ROLE_SALES_AGENT,
    ROLE_SUPPORT_AGENT,
    SOURCE_DECLARED,
)
from app.products.resolver import resolve_config

# A clinic, deliberately nothing like NekoSalesAI. The price must not coincide
# with a storefront price, or a leak would pass unnoticed.
CLINIC_PAYLOAD = {
    "company_name": "Bright Dental",
    "agent_name": "Tolu from Bright Dental",
    "tagline": "Same-week appointments.",
    "support_email": "care@brightdental.ng",
    "plans": [
        {
            "code": "cleaning",
            "name": "Scale and Polish",
            "audience": "Anyone due a clean",
            "currency": "NGN",
            "amount": "18500.50",
            "billing_period": "visit",
        }
    ],
    "capabilities": ["Same-week appointments", "Evening slots available"],
    "faqs": [{"question": "Do you accept walk-ins?", "answer": "Yes, daily 9-5."}],
    "max_auto_discount_percent": 10,
}


@pytest.fixture
def authed_org_id(client, auth_headers, db) -> int:
    """The organization the registered test user actually belongs to."""
    user = db.query(User).filter(User.email == "founder@nekosales.ai").first()
    return user.organization_id


@pytest.fixture
def authed_profile(db, authed_org_id) -> WorkspaceProfile:
    """A provisioned workspace for the caller — what intake writes into."""
    profile = WorkspaceProfile(
        organization_id=authed_org_id,
        plan_code="growth_monthly",
        status=PROVISION_READY,
        agent_name="Sales Rep",
        company_name="Customer Co",
        greeting="Hi there",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def test_get_config_before_intake_sells_nothing(client, auth_headers, authed_profile):
    response = client.get("/api/v1/product-config", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "Customer Co"
    # No plans yet: the customer learns their product is unfinished here
    # rather than from a buyer who got escalated.
    assert data["sells_anything"] is False
    assert data["plans"] == []


def test_put_config_stores_and_returns_it(client, auth_headers, authed_profile):
    response = client.put(
        "/api/v1/product-config", json=CLINIC_PAYLOAD, headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "Bright Dental"
    assert data["agent_name"] == "Tolu from Bright Dental"
    assert len(data["plans"]) == 1
    assert data["plans"][0]["code"] == "cleaning"
    assert data["plans"][0]["billing_period"] == "visit"
    assert data["sells_anything"] is True


def test_money_survives_as_exact_minor_units(client, auth_headers, authed_profile):
    response = client.put(
        "/api/v1/product-config", json=CLINIC_PAYLOAD, headers=auth_headers
    )

    plan = response.json()["plans"][0]
    assert plan["amount_minor"] == 1_850_050
    assert plan["display_price"] == "₦18,500.50"


def test_intake_capabilities_are_always_declared(client, auth_headers, authed_profile):
    """A customer cannot get their marketing copy stated in our voice."""
    response = client.put(
        "/api/v1/product-config", json=CLINIC_PAYLOAD, headers=auth_headers
    )

    capabilities = response.json()["capabilities"]
    assert len(capabilities) == 2
    assert all(c["source"] == SOURCE_DECLARED for c in capabilities)
    assert all(c["verified_by"] == "" for c in capabilities)


def test_a_payload_cannot_request_verification(client, auth_headers, authed_profile):
    """Even spelled out explicitly, the claim comes back declared."""
    payload = dict(CLINIC_PAYLOAD)
    payload["capabilities"] = ["We are FDA approved"]

    response = client.put("/api/v1/product-config", json=payload, headers=auth_headers)

    capability = response.json()["capabilities"][0]
    assert capability["source"] == SOURCE_DECLARED
    assert capability["verified_by"] == ""


def test_config_with_no_plans_reports_selling_nothing(
    client, auth_headers, authed_profile
):
    response = client.put(
        "/api/v1/product-config",
        json={"company_name": "No Plans Yet", "plans": []},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["sells_anything"] is False


def test_intake_without_a_provisioned_workspace_is_404(client, auth_headers):
    """No workspace means nothing to configure — not a silent no-op."""
    response = client.put(
        "/api/v1/product-config", json=CLINIC_PAYLOAD, headers=auth_headers
    )

    assert response.status_code == 404
    assert "no provisioned workspace" in response.json()["detail"]


def test_duplicate_plan_codes_are_rejected_as_422(client, auth_headers, authed_profile):
    """Two plans sharing a code would make a quote and its payment disagree."""
    response = client.put(
        "/api/v1/product-config",
        json={
            "company_name": "Duplicate Plans",
            "plans": [
                {"code": "same", "name": "A", "amount": "100"},
                {"code": "same", "name": "B", "amount": "200"},
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_unchargeable_currency_is_rejected(client, auth_headers, authed_profile):
    response = client.put(
        "/api/v1/product-config",
        json={
            "company_name": "Wrong Money",
            "plans": [
                {"code": "a", "name": "A", "amount": "100", "currency": "XPD"}
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_config_requires_authentication(client, authed_profile):
    assert client.get("/api/v1/product-config").status_code in (401, 403)
    assert client.put("/api/v1/product-config", json=CLINIC_PAYLOAD).status_code in (
        401,
        403,
    )


def test_saved_intake_governs_the_agent(client, auth_headers, authed_profile, db):
    """The point of the whole stage: the form changes what the agent says."""
    from app.sales.service import ConversationService

    client.put("/api/v1/product-config", json=CLINIC_PAYLOAD, headers=auth_headers)

    conversation = ConversationService(db).start(authed_profile.organization_id)
    greeting = conversation.messages[0].body

    assert "Bright Dental" in greeting
    assert "Tolu" in greeting
    # The storefront's identity must not appear in a customer's conversation.
    assert "NekoSalesAI" not in greeting


def test_one_org_cannot_reach_another_orgs_config(
    client, auth_headers, authed_profile, db
):
    """Writing as one tenant must leave every other tenant untouched."""
    other_org = Organization(name="Other Co", slug="other-co")
    db.add(other_org)
    db.commit()
    db.refresh(other_org)

    other_profile = WorkspaceProfile(
        organization_id=other_org.id,
        plan_code="starter_monthly",
        status=PROVISION_READY,
        agent_name="Other Rep",
        company_name="Other Co",
        greeting="Hello",
    )
    db.add(other_profile)
    db.commit()

    client.put("/api/v1/product-config", json=CLINIC_PAYLOAD, headers=auth_headers)

    assert client.get("/api/v1/product-config", headers=auth_headers).json()[
        "company_name"
    ] == "Bright Dental"

    # The other tenant kept its own identity and gained no plans.
    other_config = resolve_config(db, other_org.id)
    assert other_config.company_name == "Other Co"
    assert other_config.plans == ()
    assert other_config.sells_anything is False


# ---------- intake cannot grant its own permissions ----------


@pytest.fixture
def support_profile(db, authed_org_id) -> WorkspaceProfile:
    """A provisioned support agent — a workspace that must not sell."""
    profile = WorkspaceProfile(
        organization_id=authed_org_id,
        plan_code="quote_qt_support",
        role=ROLE_SUPPORT_AGENT,
        status=PROVISION_READY,
        agent_name="Remi",
        company_name="Bright Dental",
        greeting="Hi there",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def test_intake_cannot_promote_a_support_agent_into_a_seller(
    client, auth_headers, support_profile, db, authed_org_id
):
    """The hole this closes: a support agent's owner posting a full price list
    and getting an agent that quotes it. They bought support, not sales."""
    response = client.put(
        "/api/v1/product-config", json=CLINIC_PAYLOAD, headers=auth_headers
    )

    assert response.status_code == 200
    # Their plans are stored — they are allowed to describe their business.
    assert len(response.json()["plans"]) == 1
    # But the agent still may not sell from them.
    assert response.json()["sells_anything"] is False

    resolved = resolve_config(db, authed_org_id)
    assert resolved.role == ROLE_SUPPORT_AGENT
    assert resolved.can_sell is False


def test_an_explicit_role_in_the_payload_is_ignored(
    client, auth_headers, support_profile, db, authed_org_id
):
    """Belt and braces: even if a future schema accepted the field."""
    payload = dict(CLINIC_PAYLOAD, role="sales_agent")

    response = client.put(
        "/api/v1/product-config", json=payload, headers=auth_headers
    )

    assert response.status_code == 200
    assert resolve_config(db, authed_org_id).role == ROLE_SUPPORT_AGENT


def test_a_sales_agents_intake_keeps_selling(
    client, auth_headers, authed_profile, db, authed_org_id
):
    """The guard must not break the product that is supposed to sell."""
    response = client.put(
        "/api/v1/product-config", json=CLINIC_PAYLOAD, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["sells_anything"] is True

    resolved = resolve_config(db, authed_org_id)
    assert resolved.role == ROLE_SALES_AGENT
    assert resolved.can_sell is True


def test_a_tampered_role_column_reads_as_a_support_agent(
    db, authed_org_id, authed_profile
):
    """Everywhere else junk falls back to the sales agent. Not here: this
    fallback decides permission, so it fails closed."""
    authed_profile.role = "sales_agent_but_better"
    db.commit()

    resolved = resolve_config(db, authed_org_id)

    assert resolved.role == ROLE_SUPPORT_AGENT
    assert resolved.can_sell is False


def test_a_stored_config_claiming_to_be_a_seller_does_not_become_one(
    db, authed_org_id, support_profile
):
    """The direct attack: edit config_json's role in the database."""
    stored = json.loads(support_profile.config_json or "{}")
    stored.update({"company_name": "Bright Dental", "role": "sales_agent"})
    support_profile.config_json = json.dumps(stored)
    db.commit()

    resolved = resolve_config(db, authed_org_id)

    assert resolved.role == ROLE_SUPPORT_AGENT
    assert resolved.can_sell is False
