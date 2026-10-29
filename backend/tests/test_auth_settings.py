from app.auth.security import verify_password
from app.models.user import User

PROFILE_URL = "/api/v1/auth/profile"
CHANGE_PASSWORD_URL = "/api/v1/auth/change-password"
CURRENT_PASSWORD = "SettingsPass123"


def _register_and_authenticate(client, email="settings@example.com"):
    credentials = {
        "full_name": "Settings User",
        "email": email,
        "password": CURRENT_PASSWORD,
    }
    registration = client.post("/api/v1/auth/register", json=credentials)
    assert registration.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": CURRENT_PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_update_profile_updates_name_and_organization(client, db):
    auth_headers = _register_and_authenticate(client)
    response = client.put(
        PROFILE_URL,
        json={"full_name": "Updated Founder", "company_name": "Updated Workspace"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Updated Founder"
    assert body["organization_name"] == "Updated Workspace"
    assert body["email"] == "settings@example.com"

    user = db.query(User).filter_by(email="settings@example.com").one()
    assert user.full_name == "Updated Founder"
    assert user.organization.name == "Updated Workspace"


def test_update_profile_requires_authentication(client):
    response = client.put(
        PROFILE_URL,
        json={"full_name": "Updated Founder", "company_name": "Updated Workspace"},
    )

    # HTTPBearer's default unauthenticated response in this app is 403.
    assert response.status_code == 403


def test_change_password_verifies_and_stores_new_password(client, db):
    auth_headers = _register_and_authenticate(client)
    response = client.post(
        CHANGE_PASSWORD_URL,
        json={"current_password": CURRENT_PASSWORD, "new_password": "NewPassword456"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Password updated successfully."}

    user = db.query(User).filter_by(email="settings@example.com").one()
    assert verify_password("NewPassword456", user.password_hash)
    assert not verify_password(CURRENT_PASSWORD, user.password_hash)


def test_change_password_rejects_wrong_current_password(client, db):
    auth_headers = _register_and_authenticate(client)
    user = db.query(User).filter_by(email="settings@example.com").one()
    original_hash = user.password_hash

    response = client.post(
        CHANGE_PASSWORD_URL,
        json={"current_password": "WrongPassword123", "new_password": "NewPassword456"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Current password is incorrect."
    db.refresh(user)
    assert user.password_hash == original_hash


def test_change_password_requires_authentication(client):
    response = client.post(
        CHANGE_PASSWORD_URL,
        json={"current_password": CURRENT_PASSWORD, "new_password": "NewPassword456"},
    )

    # HTTPBearer's default unauthenticated response in this app is 403.
    assert response.status_code == 403
