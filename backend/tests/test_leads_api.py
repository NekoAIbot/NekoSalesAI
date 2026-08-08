"""Regression tests for the leads API.

These routes previously returned hardcoded strings ({"message": "List Leads"})
with no database access at all, so every assertion here would have failed
against the old implementation.
"""


def lead_payload(organization_id: int, **overrides) -> dict:
    payload = {
        "organization_id": organization_id,
        "first_name": "Ada",
        "last_name": "Okafor",
        "email": "ada@warmlead.co",
        "company": "Warm Lead Co",
        "job_title": "Founder",
        "source": "Landing Page",
        "status": "New",
    }
    payload.update(overrides)
    return payload


def test_create_lead_persists_and_returns_id(client, organization):
    response = client.post(
        "/api/v1/leads/",
        json=lead_payload(organization.id),
    )

    assert response.status_code == 201

    body = response.json()
    assert body["id"] > 0
    assert body["first_name"] == "Ada"
    assert body["company"] == "Warm Lead Co"


def test_list_leads_returns_created_rows(client, organization):
    client.post("/api/v1/leads/", json=lead_payload(organization.id))
    client.post(
        "/api/v1/leads/",
        json=lead_payload(organization.id, first_name="Bilal", email="bilal@warmlead.co"),
    )

    response = client.get("/api/v1/leads/")

    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {lead["first_name"] for lead in body} == {"Ada", "Bilal"}


def test_list_leads_filters_by_status(client, organization):
    client.post("/api/v1/leads/", json=lead_payload(organization.id, status="New"))
    client.post(
        "/api/v1/leads/",
        json=lead_payload(
            organization.id,
            first_name="Chidi",
            email="chidi@warmlead.co",
            status="Converted",
        ),
    )

    response = client.get("/api/v1/leads/", params={"status": "Converted"})

    assert response.status_code == 200

    body = response.json()
    assert len(body) == 1
    assert body[0]["first_name"] == "Chidi"


def test_get_lead_returns_the_requested_row(client, organization):
    created = client.post(
        "/api/v1/leads/",
        json=lead_payload(organization.id),
    ).json()

    response = client.get(f"/api/v1/leads/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_lead_returns_404(client, organization):
    response = client.get("/api/v1/leads/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Lead not found."


def test_update_lead_applies_partial_changes(client, organization):
    created = client.post(
        "/api/v1/leads/",
        json=lead_payload(organization.id),
    ).json()

    response = client.put(
        f"/api/v1/leads/{created['id']}",
        json={"status": "Qualified"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "Qualified"
    # Unspecified fields must be preserved, not blanked.
    assert body["first_name"] == "Ada"
    assert body["company"] == "Warm Lead Co"


def test_update_missing_lead_returns_404(client, organization):
    response = client.put("/api/v1/leads/99999", json={"status": "Qualified"})

    assert response.status_code == 404


def test_delete_lead_removes_it(client, organization):
    created = client.post(
        "/api/v1/leads/",
        json=lead_payload(organization.id),
    ).json()

    assert client.delete(f"/api/v1/leads/{created['id']}").status_code == 204
    assert client.get(f"/api/v1/leads/{created['id']}").status_code == 404


def test_delete_missing_lead_returns_404(client, organization):
    response = client.delete("/api/v1/leads/99999")

    assert response.status_code == 404


def test_create_lead_rejects_missing_required_fields(client, organization):
    response = client.post(
        "/api/v1/leads/",
        json={"organization_id": organization.id, "first_name": "OnlyFirst"},
    )

    assert response.status_code == 422
