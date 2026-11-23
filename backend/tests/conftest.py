"""Shared test fixtures.

Every test runs against an in-memory SQLite database created from
Base.metadata, never the development database. The get_db dependency is
overridden so route handlers and their services use the same session the test
asserts against.

StaticPool keeps every connection pointed at the same in-memory database —
without it each connection would get its own empty one.
"""

import secrets
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import settings
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import Organization, User

# The suite runs the deterministic engine only. A live GROQ_API_KEY in the
# developer's .env would otherwise rephrase every reply and call the provider
# from the LLM slow path, making copy assertions meaningless and the run
# both slow and non-deterministic.
settings.TESTING = True
settings.ENVIRONMENT = "test"

# The suite uses the memory transport by default so no test can quietly connect
# to SMTP or post to the internet, regardless of the developer's .env.
settings.MAIL_BACKEND = "memory"


def _verify_safe_test_database(engine) -> None:
    """Ensure cleanup can NEVER execute against production or staging databases."""
    if not settings.TESTING:
        raise RuntimeError(
            "Safety check failed: settings.TESTING is not True. Refusing database cleanup."
        )

    env = getattr(settings, "ENVIRONMENT", "").lower()
    if env not in ("test", "testing"):
        raise RuntimeError(
            f"Safety check failed: ENVIRONMENT is '{env}', expected 'test'. Refusing database cleanup."
        )

    if engine.dialect.name == "postgresql":
        url = engine.url
        database_name = (url.database or "").lower()
        host = (url.host or "").lower()

        prohibited_host_keywords = (
            "render.com",
            "neon.tech",
            "aws",
            "rds",
        )
        for keyword in prohibited_host_keywords:
            if keyword in host:
                raise RuntimeError(
                    f"Safety check failed: Prohibited keyword '{keyword}' found in database host ({host}). "
                    "Refusing database cleanup."
                )

        prohibited_name_keywords = (
            "prod",
            "production",
            "stage",
            "staging",
        )
        for keyword in prohibited_name_keywords:
            if keyword in database_name or keyword in host:
                raise RuntimeError(
                    f"Safety check failed: Prohibited keyword '{keyword}' found in database host/name "
                    f"({host}/{database_name}). Refusing database cleanup."
                )

        if "test" not in database_name and database_name != "neko_test":
            raise RuntimeError(
                f"Safety check failed: PostgreSQL database name '{database_name}' does not contain 'test'. "
                "Refusing database cleanup."
            )


def _clean_database(engine) -> None:
    """Clean all application tables while preserving alembic_version and schema."""
    _verify_safe_test_database(engine)

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("SET lock_timeout = '5s';"))
            result = conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                )
            )
            tables = [row[0] for row in result.fetchall()]
            if tables:
                table_list = ", ".join(f'"{t}"' for t in tables)
                conn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE;"))
    elif engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF;"))
            for table in Base.metadata.tables.keys():
                if table != "alembic_version":
                    conn.execute(text(f'DELETE FROM "{table}";'))
            conn.execute(text("PRAGMA foreign_keys = ON;"))


@pytest.fixture
def db_engine(tmp_path):
    if not settings.is_sqlite:
        from app.database.database import engine
        yield engine
    else:
        db_file = tmp_path / f"test_{secrets.token_hex(4)}.db"
        test_engine = create_engine(
            f"sqlite:///{db_file}?timeout=30",
            connect_args={"check_same_thread": False},
        )
        with test_engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.commit()

        # Importing app.models registers every table on Base.metadata.
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=test_engine)

        yield test_engine

        test_engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(db_engine):
    """Ensure complete database isolation before and after each test case."""
    _clean_database(db_engine)
    try:
        yield
    finally:
        _clean_database(db_engine)


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
def auth_headers(client, db) -> dict[str, str]:
    credentials = {
        "full_name": "Test Founder",
        "email": "founder@nekosales.ai",
        "password": "Str0ngPass!2026",
    }

    client.post("/api/v1/auth/register", json=credentials)

    user = db.query(User).filter_by(email=credentials["email"]).first()
    if user:
        user.email_verified = True
        db.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": credentials["email"],
            "password": credentials["password"],
        },
    )

    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}
