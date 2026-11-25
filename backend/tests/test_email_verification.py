"""Dedicated tests for organic customer email verification and mail security."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import re
import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth.service import AuthService, EMAIL_CODE_MAX_ATTEMPTS
from app.config.settings import Settings, settings as live_settings
from app.database.base import Base
from app.mail.transport import ConsoleMailTransport, Message, build_transport
from app.models.email_verification_code import EmailVerificationCode
from app.models.user import User
from app.repositories.user_repository import UserRepository

PASSWORD = "VerifyPass2026!Secure"


def _wait_for_otp(outbox, recipient_email: str, timeout: float = 2.0) -> tuple[str, Message]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for msg in reversed(outbox.outbox):
            if msg.to.lower() == recipient_email.lower():
                match = re.search(r"\b(\d{6})\b", msg.body)
                if match:
                    return match.group(1), msg
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for OTP email to {recipient_email}")


def _register_user(client, outbox, email: str = "buyer@example.com") -> tuple[dict, str, Message]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ada Lovelace",
            "email": email,
            "password": PASSWORD,
            "company_name": "Analytical Engines Ltd",
        },
    )
    assert resp.status_code == 201, resp.text
    otp, msg = _wait_for_otp(outbox, email)
    return resp.json(), otp, msg


def test_otp_generation_delivery_and_subject_redaction(client, db, outbox):
    body, otp, msg = _register_user(client, outbox, "otp-gen@example.com")

    # OTP is never returned in registration response or email subject.
    assert otp not in str(body)
    assert otp not in msg.subject
    assert msg.subject == "Your Nera verification code"
    assert len(otp) == 6 and otp.isdigit()

    # Stored OTP is hashed, not plaintext.
    user = db.query(User).filter_by(email="otp-gen@example.com").one()
    record = db.query(EmailVerificationCode).filter_by(user_id=user.id).one()
    assert record.code_hash != otp
    assert otp not in record.code_hash
    assert user.email_verified is False


def test_unverified_login_rejected_then_allowed_after_verify(client, outbox):
    _register_user(client, outbox, "unverified@example.com")

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "unverified@example.com", "password": PASSWORD},
    )
    assert blocked.status_code == 403
    assert "verification" in blocked.json()["detail"].lower()

    otp, _ = _wait_for_otp(outbox, "unverified@example.com")
    verify_resp = client.post(
        "/api/v1/auth/email-verification/verify",
        json={"email": "unverified@example.com", "code": otp},
    )
    assert verify_resp.status_code == 200

    allowed = client.post(
        "/api/v1/auth/login",
        json={"email": "unverified@example.com", "password": PASSWORD},
    )
    assert allowed.status_code == 200
    assert allowed.json()["access_token"]


def test_incorrect_verification_code_rejected(client, outbox):
    _, otp, _ = _register_user(client, outbox, "wrong-code@example.com")
    wrong = "000000" if otp != "000000" else "999999"

    resp = client.post(
        "/api/v1/auth/email-verification/verify",
        json={"email": "wrong-code@example.com", "code": wrong},
    )
    assert resp.status_code == 400
    assert "invalid code" in resp.json()["detail"].lower()


def test_expired_verification_code_rejected(client, db, outbox):
    _, otp, _ = _register_user(client, outbox, "expired@example.com")
    user = db.query(User).filter_by(email="expired@example.com").one()
    record = db.query(EmailVerificationCode).filter_by(user_id=user.id).one()
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    resp = client.post(
        "/api/v1/auth/email-verification/verify",
        json={"email": "expired@example.com", "code": otp},
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_resend_cooldown_enforced_and_new_code_works_after_cooldown(client, db, outbox):
    _, first_otp, _ = _register_user(client, outbox, "cooldown@example.com")

    # Immediate resend is blocked by 60-second cooldown.
    too_soon = client.post(
        "/api/v1/auth/email-verification/send",
        json={"email": "cooldown@example.com"},
    )
    assert too_soon.status_code == 400
    assert "wait" in too_soon.json()["detail"].lower()

    # Simulate cooldown elapsed.
    user = db.query(User).filter_by(email="cooldown@example.com").one()
    record = db.query(EmailVerificationCode).filter_by(user_id=user.id).one()
    record.created_at = datetime.now(UTC) - timedelta(seconds=65)
    db.commit()

    outbox.clear()
    resend_ok = client.post(
        "/api/v1/auth/email-verification/send",
        json={"email": "cooldown@example.com"},
    )
    assert resend_ok.status_code == 200
    second_otp, _ = _wait_for_otp(outbox, "cooldown@example.com")

    # Previous code is invalidated when a new one is issued (unless identical by 1-in-10^6 chance).
    if second_otp != first_otp:
        old_resp = client.post(
            "/api/v1/auth/email-verification/verify",
            json={"email": "cooldown@example.com", "code": first_otp},
        )
        assert old_resp.status_code == 400

    new_resp = client.post(
        "/api/v1/auth/email-verification/verify",
        json={"email": "cooldown@example.com", "code": second_otp},
    )
    assert new_resp.status_code == 200


def test_attempt_limit_enforced_sequentially_and_concurrently(tmp_path):
    # Use a file-backed WAL SQLite DB so each worker thread has its own connection.
    db_file = tmp_path / "concurrent_verify.db"
    engine = create_engine(
        f"sqlite:///{db_file}?timeout=30",
        connect_args={"check_same_thread": False},
    )
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # Seed user + verification code without background email thread dependency.
    seed_session = factory()
    try:
        from app.auth.schemas import RegisterRequest
        from app.mail import MemoryMailTransport, set_transport

        transport = MemoryMailTransport()
        set_transport(transport)
        try:
            service = AuthService(UserRepository(seed_session), seed_session)
            service.register(
                RegisterRequest(
                    full_name="Concurrent User",
                    email="attempts@example.com",
                    password=PASSWORD,
                    company_name="Concurrent Co",
                )
            )
            otp, _ = _wait_for_otp(transport, "attempts@example.com")
        finally:
            set_transport(None)
    finally:
        seed_session.close()

    wrong = "000000" if otp != "000000" else "999999"

    def _attempt(code: str) -> str:
        session = factory()
        try:
            service = AuthService(UserRepository(session), session)
            service.verify_email("attempts@example.com", code)
            return "ok"
        except ValueError as exc:
            return str(exc)
        finally:
            session.close()

    try:
        # Fire 6 concurrent wrong attempts; at most EMAIL_CODE_MAX_ATTEMPTS (3) can consume attempts.
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: _attempt(wrong), range(6)))

        invalid_count = sum(1 for r in results if r == "Invalid code.")
        locked_count = sum(1 for r in results if "Too many attempts" in r)
        assert invalid_count == EMAIL_CODE_MAX_ATTEMPTS
        assert locked_count == 6 - EMAIL_CODE_MAX_ATTEMPTS

        # Even the valid code is now rejected because max attempts are exhausted.
        assert "too many attempts" in _attempt(otp).lower()
    finally:
        engine.dispose()


def test_single_use_and_cross_account_isolation(client, db, outbox):
    _, otp_a, _ = _register_user(client, outbox, "user-a@example.com")
    _register_user(client, outbox, "user-b@example.com")

    # User B cannot redeem User A's OTP.
    cross = client.post(
        "/api/v1/auth/email-verification/verify",
        json={"email": "user-b@example.com", "code": otp_a},
    )
    assert cross.status_code == 400

    # User A redeems their OTP once.
    first = client.post(
        "/api/v1/auth/email-verification/verify",
        json={"email": "user-a@example.com", "code": otp_a},
    )
    assert first.status_code == 200

    # Reusing User A's OTP fails and the DB row is deleted.
    second = client.post(
        "/api/v1/auth/email-verification/verify",
        json={"email": "user-a@example.com", "code": otp_a},
    )
    assert second.status_code == 400
    user_a = db.query(User).filter_by(email="user-a@example.com").one()
    assert db.query(EmailVerificationCode).filter_by(user_id=user_a.id).first() is None


def test_non_enumeration_on_unknown_email_send(client, outbox):
    resp = client.post(
        "/api/v1/auth/email-verification/send",
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Verification code sent."
    time.sleep(0.05)
    assert len(outbox.outbox) == 0


def test_production_mail_safety_enforced(monkeypatch):
    # Settings validation rejects console/memory and unconfigured providers in production.
    with pytest.raises(RuntimeError, match="forbidden in production"):
        Settings(ENVIRONMENT="production", MAIL_BACKEND="console").validate_mail_environment()

    with pytest.raises(RuntimeError, match="forbidden in production"):
        Settings(ENVIRONMENT="production", MAIL_BACKEND="memory").validate_mail_environment()

    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        Settings(ENVIRONMENT="production", MAIL_BACKEND="smtp", SMTP_HOST="").validate_mail_environment()

    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        Settings(ENVIRONMENT="production", MAIL_BACKEND="brevo", BREVO_API_KEY="").validate_mail_environment()

    # Valid production configurations pass.
    Settings(ENVIRONMENT="production", MAIL_BACKEND="smtp", SMTP_HOST="smtp.example.com").validate_mail_environment()
    Settings(ENVIRONMENT="production", MAIL_BACKEND="brevo", BREVO_API_KEY="xkeysib-test").validate_mail_environment()

    # Transport layer itself also blocks console/memory in production.
    monkeypatch.setattr(live_settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="forbidden in production"):
        build_transport("console")
    with pytest.raises(RuntimeError, match="forbidden in production"):
        ConsoleMailTransport()._deliver(Message(to="a@b.com", subject="Test", body="Body"))


def test_verify_email_spa_route_serves_app_shell(client):
    resp = client.get("/verify-email")
    assert resp.status_code == 200
    assert "/frontend/app/main.js" in resp.text
    assert 'id="app"' in resp.text
