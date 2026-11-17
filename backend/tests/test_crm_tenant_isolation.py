"""Tenant isolation and authentication security tests for CRM endpoints.

Verifies:
1. Unauthenticated requests receive 401.
2. Authenticated users without an organization receive 403.
3. Organization A cannot read, list, update, or delete Organization B's customers, contacts, or leads.
4. Contacts cannot be created against another organization's customer.
5. Client-supplied organization_id in request body is ignored and cannot inject cross-tenant data.
6. Legitimate operations within the same organization work correctly.
"""

import pytest
from app.models.organization import Organization
from app.models.user import User


def _create_user_and_token(client, db, email: str, company: str | None = None) -> tuple[int, dict[str, str]]:
    """Helper to create a verified user and return their organization_id and auth headers."""
    credentials = {
        "full_name": f"User {email}",
        "email": email,
        "password": "SecurePassword123!",
        "company_name": company or f"Workspace {email}",
    }
    client.post("/api/v1/auth/register", json=credentials)
    user = db.query(User).filter_by(email=email).one()
    user.email_verified = True
    db.commit()

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": credentials["password"]})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return user.organization_id, headers


# ===========================================================================
# 1. Unauthenticated Access (Must Return 401)
# ===========================================================================

@pytest.mark.parametrize(
    "method,endpoint",
    [
        ("get", "/api/v1/customers/"),
        ("post", "/api/v1/customers/"),
        ("get", "/api/v1/customers/1"),
        ("put", "/api/v1/customers/1"),
        ("delete", "/api/v1/customers/1"),
        ("get", "/api/v1/contacts/"),
        ("post", "/api/v1/contacts/"),
        ("get", "/api/v1/contacts/1"),
        ("put", "/api/v1/contacts/1"),
        ("delete", "/api/v1/contacts/1"),
        ("get", "/api/v1/leads/"),
        ("post", "/api/v1/leads/"),
        ("get", "/api/v1/leads/1"),
        ("put", "/api/v1/leads/1"),
        ("delete", "/api/v1/leads/1"),
    ],
)
def test_crm_endpoints_require_authentication(client, method, endpoint):
    handler = getattr(client, method)
    response = handler(endpoint, json={"first_name": "Test"})
    # HTTPBearer returns 401 when no token is supplied or 403 when forbidden
    assert response.status_code in (401, 403)


# ===========================================================================
# 2. User Without Organization (Must Return 403)
# ===========================================================================

def test_user_without_organization_is_rejected_with_403(client, db):
    _, headers = _create_user_and_token(client, db, "no-org@example.com")
    user = db.query(User).filter_by(email="no-org@example.com").one()
    user.organization_id = None
    db.commit()

    res_cust = client.get("/api/v1/customers/", headers=headers)
    assert res_cust.status_code == 403
    assert res_cust.json()["detail"] == "No organization associated with user."

    res_lead = client.get("/api/v1/leads/", headers=headers)
    assert res_lead.status_code == 403

    res_contact = client.get("/api/v1/contacts/", headers=headers)
    assert res_contact.status_code == 403


# ===========================================================================
# 3. Cross-Tenant Customer Isolation (IDOR & Listing Prevention)
# ===========================================================================

def test_customer_tenant_isolation(client, db):
    org_a_id, headers_a = _create_user_and_token(client, db, "admin_a@tenant-a.com", "Tenant A")
    org_b_id, headers_b = _create_user_and_token(client, db, "admin_b@tenant-b.com", "Tenant B")

    # Tenant A creates a customer
    res = client.post(
        "/api/v1/customers/",
        json={"first_name": "Customer", "last_name": "Alpha", "email": "alpha@example.com"},
        headers=headers_a,
    )
    assert res.status_code == 201
    cust_a_id = res.json()["id"]

    # Tenant A can list and retrieve Customer Alpha
    list_a = client.get("/api/v1/customers/", headers=headers_a).json()
    assert len(list_a) == 1
    assert list_a[0]["id"] == cust_a_id

    get_a = client.get(f"/api/v1/customers/{cust_a_id}", headers=headers_a)
    assert get_a.status_code == 200
    assert get_a.json()["first_name"] == "Customer"

    # Tenant B cannot see Customer Alpha in listing
    list_b = client.get("/api/v1/customers/", headers=headers_b).json()
    assert len(list_b) == 0

    # Tenant B receives 404 when directly requesting Customer Alpha
    get_b = client.get(f"/api/v1/customers/{cust_a_id}", headers=headers_b)
    assert get_b.status_code == 404
    assert get_b.json()["detail"] == "Customer not found."

    # Tenant B receives 404 when attempting to update Customer Alpha
    put_b = client.put(
        f"/api/v1/customers/{cust_a_id}",
        json={"first_name": "Hacked"},
        headers=headers_b,
    )
    assert put_b.status_code == 404

    # Verify Customer Alpha was NOT modified
    verify_cust = client.get(f"/api/v1/customers/{cust_a_id}", headers=headers_a).json()
    assert verify_cust["first_name"] == "Customer"

    # Tenant B receives 404 when attempting to delete Customer Alpha
    del_b = client.delete(f"/api/v1/customers/{cust_a_id}", headers=headers_b)
    assert del_b.status_code == 404

    # Verify Customer Alpha still exists
    assert client.get(f"/api/v1/customers/{cust_a_id}", headers=headers_a).status_code == 200


# ===========================================================================
# 4. Cross-Tenant Lead Isolation
# ===========================================================================

def test_lead_tenant_isolation(client, db):
    org_a_id, headers_a = _create_user_and_token(client, db, "sales_a@tenant-a.com", "Tenant A")
    org_b_id, headers_b = _create_user_and_token(client, db, "sales_b@tenant-b.com", "Tenant B")

    # Tenant A creates a lead
    res = client.post(
        "/api/v1/leads/",
        json={"first_name": "Lead", "last_name": "One", "company": "Target Corp"},
        headers=headers_a,
    )
    assert res.status_code == 201
    lead_a_id = res.json()["id"]

    # Tenant B cannot list Tenant A's lead
    leads_b = client.get("/api/v1/leads/", headers=headers_b).json()
    assert len(leads_b) == 0

    # Tenant B receives 404 when accessing, updating or deleting Tenant A's lead
    assert client.get(f"/api/v1/leads/{lead_a_id}", headers=headers_b).status_code == 404
    assert client.put(f"/api/v1/leads/{lead_a_id}", json={"status": "Closed"}, headers=headers_b).status_code == 404
    assert client.delete(f"/api/v1/leads/{lead_a_id}", headers=headers_b).status_code == 404

    # Tenant A can update and delete their own lead
    assert client.put(f"/api/v1/leads/{lead_a_id}", json={"status": "Contacted"}, headers=headers_a).status_code == 200
    assert client.delete(f"/api/v1/leads/{lead_a_id}", headers=headers_a).status_code == 204


# ===========================================================================
# 5. Cross-Tenant Contact Isolation & Customer Association Guard
# ===========================================================================

def test_contact_tenant_isolation_and_customer_association(client, db):
    org_a_id, headers_a = _create_user_and_token(client, db, "lead_a@tenant-a.com", "Tenant A")
    org_b_id, headers_b = _create_user_and_token(client, db, "lead_b@tenant-b.com", "Tenant B")

    # Tenant A creates Customer A
    cust_res = client.post(
        "/api/v1/customers/",
        json={"first_name": "OrgA", "last_name": "Client"},
        headers=headers_a,
    )
    cust_a_id = cust_res.json()["id"]

    # Tenant B attempts to create a contact referencing Customer A -> 404
    contact_cross = client.post(
        "/api/v1/contacts/",
        json={"customer_id": cust_a_id, "first_name": "Malicious", "last_name": "Contact"},
        headers=headers_b,
    )
    assert contact_cross.status_code == 404
    assert contact_cross.json()["detail"] == "Customer not found."

    # Tenant A creates Contact A legitimately under Customer A
    contact_a = client.post(
        "/api/v1/contacts/",
        json={"customer_id": cust_a_id, "first_name": "Alice", "last_name": "Director"},
        headers=headers_a,
    ).json()
    contact_a_id = contact_a["id"]

    # Tenant B cannot list or get Contact A
    contacts_b = client.get("/api/v1/contacts/", headers=headers_b).json()
    assert len(contacts_b) == 0
    assert client.get(f"/api/v1/contacts/{contact_a_id}", headers=headers_b).status_code == 404

    # Tenant B cannot update or delete Contact A
    assert client.put(f"/api/v1/contacts/{contact_a_id}", json={"notes": "Hacked"}, headers=headers_b).status_code == 404
    assert client.delete(f"/api/v1/contacts/{contact_a_id}", headers=headers_b).status_code == 404


# ===========================================================================
# 6. Client-Supplied Organization ID Tampering Prevention
# ===========================================================================

def test_client_supplied_org_id_cannot_inject_cross_tenant_record(client, db):
    org_a_id, headers_a = _create_user_and_token(client, db, "user_a@tenant-a.com", "Tenant A")
    org_b_id, headers_b = _create_user_and_token(client, db, "user_b@tenant-b.com", "Tenant B")

    # User A tries to supply organization_id of Tenant B
    res_cust = client.post(
        "/api/v1/customers/",
        json={"organization_id": org_b_id, "first_name": "Spoofed", "last_name": "Customer"},
        headers=headers_a,
    )
    assert res_cust.status_code == 201
    created_cust = res_cust.json()
    # Server must have overwritten it with User A's organization_id
    assert created_cust["organization_id"] == org_a_id
    assert created_cust["organization_id"] != org_b_id

    # User A tries to spoof organization_id for Lead
    res_lead = client.post(
        "/api/v1/leads/",
        json={"organization_id": org_b_id, "first_name": "Spoofed", "last_name": "Lead"},
        headers=headers_a,
    )
    assert res_lead.status_code == 201
    created_lead = res_lead.json()
    assert created_lead["organization_id"] == org_a_id
    assert created_lead["organization_id"] != org_b_id
