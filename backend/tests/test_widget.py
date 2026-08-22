"""The two credentials a provisioned customer gets, and what each may do.

Provisioning issued API keys from the day it was written and nothing verified
one; it stamped "Preparing your widget" and no widget was served. A customer
could pay in full and had no way to put the thing they bought on their site.

The distinction these tests defend is the one that would be expensive to get
wrong. ``widget_token`` is public — it ships in the customer's page source — and
may only start a conversation. ``X-API-Key`` is secret and identifies the
workspace. If the secret were what the browser carried, every visitor to every
customer's site could read a credential that reconfigures the workspace.
"""

import json
import secrets

import pytest
from fastapi import HTTPException

from app.auth.api_key import workspace_from_api_key
from app.payments.provisioning import API_KEY_PREFIX_LENGTH, hash_api_key
from app.models.organization import Organization
from app.models.workspace_profile import (
    PROVISION_PENDING,
    PROVISION_READY,
    WorkspaceProfile,
)


def _config(company: str = "Bright Dental", role: str = "support_agent") -> str:
    return json.dumps(
        {
            "company_name": company,
            "agent_name": "Tola",
            "tagline": "Dental care in Yaba",
            "description": "A dental clinic.",
            "support_email": "hi@bright.example",
            "role": role,
            "plans": [],
            "capabilities": [],
            "faqs": [],
            "max_auto_discount_percent": 0,
        }
    )


@pytest.fixture
def workspace(db):
    """A live workspace with both credentials issued."""
    org = Organization(name="Bright Dental", slug="bright-dental")
    db.add(org)
    db.commit()
    db.refresh(org)

    api_key = "nsk_live_" + secrets.token_urlsafe(24)
    widget_token = secrets.token_urlsafe(18)

    profile = WorkspaceProfile(
        organization_id=org.id,
        plan_code="starter",
        role="support_agent",
        status=PROVISION_READY,
        agent_name="Tola",
        company_name="Bright Dental",
        greeting="Hi, I'm Tola at Bright Dental.",
        accent_color="#0b5fff",
        api_key_hash=hash_api_key(api_key),
        api_key_prefix=api_key[:API_KEY_PREFIX_LENGTH],
        widget_token=widget_token,
        config_json=_config(),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile, api_key, widget_token


# ---------- the secret key ----------


def test_a_valid_key_resolves_its_workspace(db, workspace):
    profile, api_key, _ = workspace

    assert workspace_from_api_key(x_api_key=api_key, db=db).id == profile.id


@pytest.mark.parametrize(
    "presented",
    [None, "", "nsk_live_completely-wrong-key-value"],
)
def test_a_missing_or_wrong_key_is_rejected(db, workspace, presented):
    with pytest.raises(HTTPException) as raised:
        workspace_from_api_key(x_api_key=presented, db=db)

    assert raised.value.status_code == 401


def test_the_right_prefix_with_the_wrong_body_is_rejected(db, workspace):
    """The prefix narrows the lookup; it is not the credential.

    Verification reads by prefix so it is an indexed row read rather than a scan
    of every workspace. That optimisation must not become the check.
    """
    _, api_key, _ = workspace
    forged = api_key[:API_KEY_PREFIX_LENGTH] + "x" * 24

    with pytest.raises(HTTPException) as raised:
        workspace_from_api_key(x_api_key=forged, db=db)

    assert raised.value.status_code == 401


def test_a_key_for_an_unprovisioned_workspace_is_refused(db, workspace):
    """Its config may be half-written, and an agent answering from a partial
    catalog is the failure app.products.resolver exists to prevent."""
    profile, api_key, _ = workspace
    profile.status = PROVISION_PENDING
    db.commit()

    with pytest.raises(HTTPException) as raised:
        workspace_from_api_key(x_api_key=api_key, db=db)

    assert raised.value.status_code == 409


# ---------- the public widget token ----------


def test_the_widget_config_carries_branding_and_no_catalog(client, db, workspace):
    """The browser gets what it needs to render and nothing it could contradict.

    Replies are composed server-side, so a widget holding the plan list would be
    keeping a copy it has no use for and could disagree with.
    """
    _, _, widget_token = workspace

    response = client.get(f"/api/v1/widget/{widget_token}/config")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_name"] == "Tola"
    assert body["company_name"] == "Bright Dental"
    assert "plans" not in body
    assert "faqs" not in body


def test_a_support_agent_is_not_advertised_as_able_to_sell(client, db, workspace):
    _, _, widget_token = workspace

    body = client.get(f"/api/v1/widget/{widget_token}/config").json()

    assert body["can_sell"] is False


def test_an_unknown_widget_token_is_a_404(client, db, workspace):
    assert client.get("/api/v1/widget/not-a-real-token/config").status_code == 404


def test_a_pending_workspace_serves_no_widget(client, db, workspace):
    """Same 404 as an unknown token, so tokens cannot be enumerated."""
    profile, _, widget_token = workspace
    profile.status = PROVISION_PENDING
    db.commit()

    assert client.get(f"/api/v1/widget/{widget_token}/config").status_code == 404


def test_the_widget_answers_from_the_customers_catalog(client, db, workspace):
    """The payoff of per-tenant config arriving before this route.

    A customer's widget quoting our price list to their buyers was the exact
    failure Stage A was built to stop.
    """
    _, _, widget_token = workspace

    started = client.post(f"/api/v1/widget/{widget_token}/conversations")

    assert started.status_code == 201
    greeting = started.json()["messages"][0]["body"]
    assert "Bright Dental" in greeting or "Tola" in greeting
    assert "NekoSalesAI" not in greeting


def test_a_widget_conversation_accepts_a_message(client, db, workspace):
    _, _, widget_token = workspace
    token = client.post(f"/api/v1/widget/{widget_token}/conversations").json()["token"]

    reply = client.post(
        f"/api/v1/widget/{widget_token}/conversations/{token}/messages",
        json={"body": "what do you charge?"},
    )

    assert reply.status_code == 201
    assert reply.json()["body"]


def test_one_widget_cannot_read_another_tenants_conversation(client, db, workspace):
    """Conversation tokens are unguessable, but that is a property of the
    generator. A route relying on it alone becomes cross-tenant the day it
    changes."""
    _, _, widget_token = workspace
    token = client.post(f"/api/v1/widget/{widget_token}/conversations").json()["token"]

    other_org = Organization(name="Other Co", slug="other-co")
    db.add(other_org)
    db.commit()
    db.refresh(other_org)

    other_token = secrets.token_urlsafe(18)
    db.add(
        WorkspaceProfile(
            organization_id=other_org.id,
            plan_code="starter",
            role="sales_agent",
            status=PROVISION_READY,
            agent_name="Someone",
            company_name="Other Co",
            greeting="Hi",
            widget_token=other_token,
            config_json=_config(company="Other Co", role="sales_agent"),
        )
    )
    db.commit()

    stolen = client.get(f"/api/v1/widget/{other_token}/conversations/{token}")

    assert stolen.status_code == 404


# ---------- cross-origin access ----------


def test_the_widget_answers_any_origin(client, db, workspace):
    """It runs on domains we cannot know in advance."""
    _, _, widget_token = workspace

    response = client.get(
        f"/api/v1/widget/{widget_token}/config",
        headers={"Origin": "https://bright.example"},
    )

    assert response.headers.get("access-control-allow-origin") == "*"


def test_the_widget_never_allows_credentials(client, db, workspace):
    """Allow-Origin: * with Allow-Credentials: true is rejected by every browser.

    Starlette's CORS middleware sets the credentials header whenever an Origin is
    present, so leaving it in place would break the widget on every customer site
    while looking correct from the server.
    """
    _, _, widget_token = workspace

    response = client.get(
        f"/api/v1/widget/{widget_token}/config",
        headers={"Origin": "https://bright.example"},
    )

    assert response.headers.get("access-control-allow-credentials") is None


def test_the_authenticated_api_keeps_its_narrow_origin_list(client):
    """The permissive policy must not have leaked past the widget prefix."""
    response = client.get(
        "/api/v1/pricing/options", headers={"Origin": "https://evil.example"}
    )

    assert response.headers.get("access-control-allow-origin") in (None, "")


def test_a_widget_preflight_succeeds(client, db, workspace):
    """OPTIONS matches no widget route, so without handling it the browser would
    get a 405 and refuse to send the real request."""
    _, _, widget_token = workspace

    response = client.options(
        f"/api/v1/widget/{widget_token}/conversations",
        headers={
            "Origin": "https://bright.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
