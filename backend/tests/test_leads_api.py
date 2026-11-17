"""Regression tests for the leads API.

These routes are authenticated and scoped to the user's organization.
"""


def lead_payload(organization_id: int | None = None, **overrides) -> dict:
    payload = {
        "first_name": "Ada",
        "last_name": "Okafor",
        "email": "ada@warmlead.co",
        "company": "Warm Lead Co",
        "job_title": "Founder",
        "source": "Landing Page",
        "status": "New",
    }
    if organization_id is not None:
        payload["organization_id"] = organization_id
    payload.update(overrides)
    return payload


def test_create_lead_persists_and_returns_id(client, auth_headers):
    response = client.post(
        "/api/v1/leads/",
        json=lead_payload(),
        headers=auth_headers,
    )

    assert response.status_code == 201

    body = response.json()
    assert body["id"] > 0
    assert body["first_name"] == "Ada"
    assert body["company"] == "Warm Lead Co"


def test_list_leads_returns_created_rows(client, auth_headers):
    client.post("/api/v1/leads/", json=lead_payload(), headers=auth_headers)
    client.post(
        "/api/v1/leads/",
        json=lead_payload(first_name="Bilal", email="bilal@warmlead.co"),
        headers=auth_headers,
    )

    response = client.get("/api/v1/leads/", headers=auth_headers)

    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {lead["first_name"] for lead in body} == {"Ada", "Bilal"}


def test_list_leads_filters_by_status(client, auth_headers):
    client.post("/api/v1/leads/", json=lead_payload(status="New"), headers=auth_headers)
    client.post(
        "/api/v1/leads/",
        json=lead_payload(
            first_name="Chidi",
            email="chidi@warmlead.co",
            status="Converted",
        ),
        headers=auth_headers,
    )

    response = client.get("/api/v1/leads/", params={"status": "Converted"}, headers=auth_headers)

    assert response.status_code == 200

    body = response.json()
    assert len(body) == 1
    assert body[0]["first_name"] == "Chidi"


def test_get_lead_returns_the_requested_row(client, auth_headers):
    created = client.post(
        "/api/v1/leads/",
        json=lead_payload(),
        headers=auth_headers,
    ).json()

    response = client.get(f"/api/v1/leads/{created['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_lead_returns_404(client, auth_headers):
    response = client.get("/api/v1/leads/99999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Lead not found."


def test_update_lead_applies_partial_changes(client, auth_headers):
    created = client.post(
        "/api/v1/leads/",
        json=lead_payload(),
        headers=auth_headers,
    ).json()

    response = client.put(
        f"/api/v1/leads/{created['id']}",
        json={"status": "Qualified"},
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "Qualified"
    # Unspecified fields must be preserved, not blanked.
    assert body["first_name"] == "Ada"
    assert body["company"] == "Warm Lead Co"


def test_update_missing_lead_returns_404(client, auth_headers):
    response = client.put("/api/v1/leads/99999", json={"status": "Qualified"}, headers=auth_headers)

    assert response.status_code == 404


def test_delete_lead_removes_it(client, auth_headers):
    created = client.post(
        "/api/v1/leads/",
        json=lead_payload(),
        headers=auth_headers,
    ).json()

    assert client.delete(f"/api/v1/leads/{created['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/leads/{created['id']}", headers=auth_headers).status_code == 404


def test_delete_missing_lead_returns_404(client, auth_headers):
    response = client.delete("/api/v1/leads/99999", headers=auth_headers)

    assert response.status_code == 404


def test_create_lead_rejects_missing_required_fields(client, auth_headers):
    response = client.post(
        "/api/v1/leads/",
        json={"first_name": "OnlyFirst"},
        headers=auth_headers,
    )

    assert response.status_code == 422
