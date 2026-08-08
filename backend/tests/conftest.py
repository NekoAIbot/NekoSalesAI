"""Shared test fixtures.

Every test runs against an in-memory SQLite database created from
Base.metadata, never the development database. The get_db dependency is
overridden so route handlers and their services use the same session the test
asserts against.

StaticPool keeps every connection pointed at the same in-memory database —
without it each connection would get its own empty one.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import Organization


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Importing app.models registers every table on Base.metadata.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    yield engine

    engine.dispose()


@pytest.fixture
def db(db_engine) -> Iterator[Session]:
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = factory()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def organization(db) -> Organization:
    org = Organization(name="Acme Ltd", slug="acme")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def auth_headers(client) -> dict[str, str]:
    credentials = {
        "full_name": "Test Founder",
        "email": "founder@nekosales.ai",
        "password": "Str0ngPass!2026",
    }

    client.post("/api/v1/auth/register", json=credentials)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": credentials["email"],
            "password": credentials["password"],
        },
    )

    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}
