"""End-to-end tests for the sales loop.

Covers the two highest-stakes paths through the API: a visitor conversation
that stays inside the catalog, and one that tries to leave it and therefore
has to stop at the approval gate.
"""

import pytest

from app.catalog import PLANS
from app.config.settings import settings
from app.models.approval_request import (
    STATUS_APPROVED,
    STATUS_DECLINED,
    STATUS_PENDING,
    ApprovalRequest,
)
from app.models.conversation import STAGE_AWAITING_APPROVAL, ROLE_HUMAN
from app.models.organization import Organization


@pytest.fixture
def storefront(db) -> Organization:
    """The org the public chat sells for, matching settings."""
    org = Organization(
        name="NekoSalesAI Demo",
        slug=settings.STOREFRONT_ORG_SLUG,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def thread(client, storefront) -> str:
    response = client.post("/api/v1/sales/conversations")
    assert response.status_code == 201
    return response.json()["token"]


@pytest.fixture
def desk_headers(client, storefront, db) -> dict[str, str]:
    """A staff user who belongs to the storefront org.

    Registration creates a fresh workspace per signup, so a desk user for an
    existing org is made by registering and then moving them into it — the
    same thing an invite flow will do.
    """
    from app.models.user import User

    credentials = {
        "full_name": "Desk Operator",
        "email": "desk@nekosales.ai",
        "password": "Str0ngPass!2026",
    }

    client.post("/api/v1/auth/register", json=credentials)

    user = db.query(User).filter(User.email == credentials["email"]).first()
    user.organization_id = storefront.id
    db.commit()

    token = client.post(
        "/api/v1/auth/login",
        json={
            "email": credentials["email"],
            "password": credentials["password"],
        },
    ).json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


def send(client, token, body):
    return client.post(
        f"/api/v1/sales/conversations/{token}/messages",
        json={"body": body},
    )


def test_catalog_endpoint_matches_the_catalog_module(client):
    response = client.get("/api/v1/sales/catalog")

    assert response.status_code == 200
    data = response.json()

    assert len(data["plans"]) == len(PLANS)

    for plan, payload in zip(PLANS, data["plans"]):
        assert payload["code"] == plan.code
        assert payload["amount_minor"] == plan.amount_minor
        assert payload["display_price"] == plan.display_price


def test_starting_a_conversation_returns_a_greeting(client, storefront):
    response = client.post("/api/v1/sales/conversations")

    assert response.status_code == 201
    data = response.json()

    assert data["token"]
    assert len(data["messages"]) == 1
    assert data["messages"][0]["role"] == "agent"
    assert data["messages"][0]["reasoning"]["rule"] == "greeting"


def test_conversation_without_storefront_org_fails_honestly(client):
    """With no org configured the API says so rather than 500-ing."""
    response = client.post("/api/v1/sales/conversations")

    assert response.status_code == 503


def test_unknown_token_is_404(client, storefront):
    response = client.get("/api/v1/sales/conversations/not-a-real-token")

    assert response.status_code == 404


def test_pricing_question_returns_published_prices(client, thread):
    response = send(client, thread, "how much does it cost?")

    assert response.status_code == 201
    data = response.json()

    for plan in PLANS:
        assert plan.display_price in data["body"]


def test_every_agent_reply_carries_reasoning(client, thread):
    for message in ["what can it do?", "how much?", "I want to buy"]:
        data = send(client, thread, message).json()

        assert data["reasoning"] is not None
        assert data["reasoning"]["rule"]
        assert data["reasoning"]["signals"]


def test_agent_reply_never_reports_a_confidence_number(client, thread):
    """Confidence would be a fabricated statistic, so the field must not exist."""
    data = send(client, thread, "how much does it cost?").json()

    assert "confidence" not in data["reasoning"]
    assert "confidence" not in data["body"].lower()


def test_empty_message_is_rejected(client, thread):
    response = client.post(
        f"/api/v1/sales/conversations/{thread}/messages",
        json={"body": "   "},
    )

    assert response.status_code in (400, 422)


def test_oversized_message_is_rejected(client, thread):
    response = client.post(
        f"/api/v1/sales/conversations/{thread}/messages",
        json={"body": "x" * 5_000},
    )

    assert response.status_code == 422


def test_discount_request_creates_a_pending_approval(client, thread, db):
    response = send(client, thread, "can I get a 40% discount?")

    assert response.status_code == 201
    assert response.json()["reasoning"]["escalated"] is True

    pending = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.status == STATUS_PENDING)
        .all()
    )

    assert len(pending) == 1
    assert "40% discount" in pending[0].requested


def test_discount_request_parks_the_conversation(client, thread, db):
    send(client, thread, "any chance of a discount?")

    conversation = client.get(f"/api/v1/sales/conversations/{thread}").json()

    assert conversation["stage"] == STAGE_AWAITING_APPROVAL


def test_approval_queue_requires_authentication(client, storefront):
    response = client.get("/api/v1/sales-desk/approvals")

    assert response.status_code in (401, 403)


def test_staff_can_see_and_approve_a_request(client, thread, desk_headers, db):
    send(client, thread, "can you do a discount for a startup?")

    listed = client.get("/api/v1/sales-desk/approvals", headers=desk_headers)
    assert listed.status_code == 200

    requests = listed.json()
    assert len(requests) == 1
    assert requests[0]["status"] == STATUS_PENDING

    decided = client.post(
        f"/api/v1/sales-desk/approvals/{requests[0]['id']}/decide",
        headers=desk_headers,
        json={
            "approve": True,
            "resolution": "We can do 10% off the annual plan this quarter.",
        },
    )

    assert decided.status_code == 200
    assert decided.json()["status"] == STATUS_APPROVED


def test_approved_resolution_is_posted_verbatim_to_the_visitor(
    client, thread, desk_headers
):
    """The human's words reach the buyer unaltered — that is the guarantee."""
    send(client, thread, "can I get a discount?")

    request_id = client.get(
        "/api/v1/sales-desk/approvals", headers=desk_headers
    ).json()[0]["id"]

    resolution = "Yes — 10% off the first year, valid until 30 September."

    client.post(
        f"/api/v1/sales-desk/approvals/{request_id}/decide",
        headers=desk_headers,
        json={"approve": True, "resolution": resolution},
    )

    messages = client.get(
        f"/api/v1/sales/conversations/{thread}"
    ).json()["messages"]

    human_messages = [m for m in messages if m["role"] == ROLE_HUMAN]

    assert len(human_messages) == 1
    assert human_messages[0]["body"] == resolution


def test_declining_still_answers_the_visitor(client, thread, desk_headers):
    send(client, thread, "can I pay in instalments?")

    request_id = client.get(
        "/api/v1/sales-desk/approvals", headers=desk_headers
    ).json()[0]["id"]

    decided = client.post(
        f"/api/v1/sales-desk/approvals/{request_id}/decide",
        headers=desk_headers,
        json={
            "approve": False,
            "resolution": "We only take payment up front at the moment.",
        },
    )

    assert decided.json()["status"] == STATUS_DECLINED

    messages = client.get(
        f"/api/v1/sales/conversations/{thread}"
    ).json()["messages"]

    assert any(m["role"] == ROLE_HUMAN for m in messages)


def test_decision_without_a_resolution_is_rejected(client, thread, desk_headers):
    """Approving with nothing to say would leave the agent improvising."""
    send(client, thread, "can I get a discount?")

    request_id = client.get(
        "/api/v1/sales-desk/approvals", headers=desk_headers
    ).json()[0]["id"]

    response = client.post(
        f"/api/v1/sales-desk/approvals/{request_id}/decide",
        headers=desk_headers,
        json={"approve": True, "resolution": ""},
    )

    assert response.status_code == 422


def test_a_request_cannot_be_decided_twice(client, thread, desk_headers):
    send(client, thread, "can I get a discount?")

    request_id = client.get(
        "/api/v1/sales-desk/approvals", headers=desk_headers
    ).json()[0]["id"]

    payload = {"approve": True, "resolution": "10% off, one time."}

    first = client.post(
        f"/api/v1/sales-desk/approvals/{request_id}/decide",
        headers=desk_headers,
        json=payload,
    )
    second = client.post(
        f"/api/v1/sales-desk/approvals/{request_id}/decide",
        headers=desk_headers,
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_visitor_email_creates_a_lead(client, thread, db):
    client.patch(
        f"/api/v1/sales/conversations/{thread}/visitor",
        json={
            "name": "Amara Obi",
            "email": "amara@brightretail.ng",
            "company": "Bright Retail",
        },
    )

    leads = client.get("/api/v1/leads/").json()
    captured = [
        lead for lead in leads if lead["email"] == "amara@brightretail.ng"
    ]

    assert len(captured) == 1
    assert captured[0]["first_name"] == "Amara"
    assert captured[0]["last_name"] == "Obi"
    assert captured[0]["source"] == "AI Chat"


def test_repeat_visitor_email_does_not_duplicate_the_lead(client, thread, db):
    for _ in range(3):
        client.patch(
            f"/api/v1/sales/conversations/{thread}/visitor",
            json={"email": "repeat@brightretail.ng"},
        )

    leads = client.get("/api/v1/leads/").json()
    matched = [
        lead for lead in leads if lead["email"] == "repeat@brightretail.ng"
    ]

    assert len(matched) == 1


def test_another_org_cannot_read_this_orgs_approvals(
    client, thread, auth_headers
):
    """Tenant isolation: the desk only ever shows the caller's own org.

    ``auth_headers`` registers a fresh user, who gets a fresh workspace. The
    storefront's pending discount request must be invisible to them — an
    empty list, not a filtered-after-the-fact one.
    """
    send(client, thread, "can I get a discount?")

    listed = client.get("/api/v1/sales-desk/approvals", headers=auth_headers)

    assert listed.status_code == 200
    assert listed.json() == []


def test_another_org_cannot_read_this_orgs_conversations(
    client, thread, auth_headers
):
    listed = client.get(
        "/api/v1/sales-desk/conversations", headers=auth_headers
    )

    assert listed.status_code == 200
    assert listed.json() == []


def test_another_org_cannot_decide_this_orgs_approval(
    client, thread, auth_headers, desk_headers
):
    """Guessing an id from another tenant must 404, not act on it."""
    send(client, thread, "can I get a discount?")

    request_id = client.get(
        "/api/v1/sales-desk/approvals", headers=desk_headers
    ).json()[0]["id"]

    response = client.post(
        f"/api/v1/sales-desk/approvals/{request_id}/decide",
        headers=auth_headers,
        json={"approve": True, "resolution": "Sure, 90% off."},
    )

    assert response.status_code == 404
