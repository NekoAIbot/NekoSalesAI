"""Regression tests for Paystack test/live environment safety rules.

Verifies:
- Development and non-production environments reject live keys ('sk_live_', 'pk_live_').
- Non-production environments require test-key prefix ('sk_test_', 'pk_test_').
- Production mode requires explicit production environment setting ('ENVIRONMENT=production').
- Mismatched key environments are rejected.
- Missing credentials fail closed.
- Secret values are never exposed or printed in exception messages.
"""

from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.payments import (
    PaymentEnvironmentError,
    PaymentsNotConfigured,
    PaystackClient,
    validate_paystack_credentials,
)


class FakeTransport:
    def request(self, method, url, *, headers, json_body=None):
        return 200, {"status": True, "data": {}}


def test_missing_secret_key_fails_closed():
    with pytest.raises(PaymentsNotConfigured):
        validate_paystack_credentials(secret_key="", environment="development")

    with pytest.raises(PaymentsNotConfigured):
        validate_paystack_credentials(secret_key="   ", environment="development")


def test_live_secret_key_in_development_rejected():
    with pytest.raises(PaymentEnvironmentError) as exc_info:
        validate_paystack_credentials(
            secret_key="sk_live_1234567890abcdef",
            environment="development",
        )
    assert "forbidden in non-production" in str(exc_info.value)
    # Ensure raw secret is not leaked in exception string
    assert "sk_live_1234567890abcdef" not in str(exc_info.value)


def test_live_public_key_in_development_rejected():
    with pytest.raises(PaymentEnvironmentError) as exc_info:
        validate_paystack_credentials(
            secret_key="sk_test_1234567890abcdef",
            public_key="pk_live_1234567890abcdef",
            environment="development",
        )
    assert "forbidden in non-production" in str(exc_info.value) or "Mismatched" in str(exc_info.value)
    assert "pk_live_1234567890abcdef" not in str(exc_info.value)


def test_invalid_prefix_in_development_rejected():
    with pytest.raises(PaymentEnvironmentError) as exc_info:
        validate_paystack_credentials(
            secret_key="invalid_prefix_key_123",
            environment="development",
        )
    assert "must use the test prefix 'sk_test_'" in str(exc_info.value)
    assert "invalid_prefix_key_123" not in str(exc_info.value)


def test_mismatched_test_secret_and_live_public_rejected():
    with pytest.raises(PaymentEnvironmentError) as exc_info:
        validate_paystack_credentials(
            secret_key="sk_test_validtestkey123",
            public_key="pk_live_validlivekey123",
            environment="development",
        )
    assert "pk_live_validlivekey123" not in str(exc_info.value)


def test_mismatched_live_secret_and_test_public_rejected():
    with pytest.raises(PaymentEnvironmentError) as exc_info:
        validate_paystack_credentials(
            secret_key="sk_live_validlivekey123",
            public_key="pk_test_validtestkey123",
            environment="production",
        )
    assert "Mismatched" in str(exc_info.value)
    assert "sk_live_validlivekey123" not in str(exc_info.value)


def test_test_secret_in_production_rejected():
    with pytest.raises(PaymentEnvironmentError) as exc_info:
        validate_paystack_credentials(
            secret_key="sk_test_1234567890abcdef",
            public_key="pk_test_1234567890abcdef",
            environment="production",
        )
    assert "Production environment requires a live Paystack secret key" in str(exc_info.value)
    assert "sk_test_1234567890abcdef" not in str(exc_info.value)


def test_valid_test_credentials_accepted_in_development():
    # Should not raise
    validate_paystack_credentials(
        secret_key="sk_test_1234567890abcdef",
        public_key="pk_test_1234567890abcdef",
        environment="development",
    )


def test_valid_live_credentials_accepted_in_production():
    # Should not raise
    validate_paystack_credentials(
        secret_key="sk_live_1234567890abcdef",
        public_key="pk_live_1234567890abcdef",
        environment="production",
    )


def test_paystack_client_fails_closed_on_live_key_in_dev():
    with pytest.raises(PaymentEnvironmentError):
        PaystackClient(
            secret_key="sk_live_some_secret_key",
            transport=FakeTransport(),
            environment="development",
        )


def test_paystack_client_empty_key_unconfigured():
    client = PaystackClient(secret_key="", transport=FakeTransport())
    assert client.is_configured is False
    with pytest.raises(PaymentsNotConfigured):
        client._headers()


def test_settings_production_mode_requires_intentional_environment():
    # Live key present, but environment is development
    dev_settings = Settings(
        ENVIRONMENT="development",
        PAYSTACK_SECRET_KEY="sk_live_test_value_123",
        PAYSTACK_PUBLIC_KEY="pk_live_test_value_123",
    )
    # paystack_is_live MUST be False in development
    assert dev_settings.paystack_is_live is False
    # payments_enabled MUST fail closed (False) when safety check fails
    assert dev_settings.payments_enabled is False

    # Valid test key in development
    test_settings = Settings(
        ENVIRONMENT="development",
        PAYSTACK_SECRET_KEY="sk_test_valid_key_123",
        PAYSTACK_PUBLIC_KEY="pk_test_valid_key_123",
    )
    assert test_settings.paystack_is_live is False
    assert test_settings.payments_enabled is True

    # Valid live key with explicit production environment
    prod_settings = Settings(
        ENVIRONMENT="production",
        PAYSTACK_SECRET_KEY="sk_live_valid_key_123",
        PAYSTACK_PUBLIC_KEY="pk_live_valid_key_123",
    )
    assert prod_settings.paystack_is_live is True
    assert prod_settings.payments_enabled is True


def test_staging_and_testing_reject_live_credentials():
    for env in ["staging", "testing", "STAGING", "Testing"]:
        with pytest.raises(PaymentEnvironmentError) as exc_info:
            validate_paystack_credentials(
                secret_key="sk_live_staging_not_allowed",
                environment=env,
            )
        assert "forbidden in non-production" in str(exc_info.value)
        assert "sk_live_staging_not_allowed" not in str(exc_info.value)


def test_checkout_config_hides_public_key_when_payments_disabled(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config.settings import settings

    # Case 1: Keys missing
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "", raising=False)
    monkeypatch.setattr(settings, "PAYSTACK_PUBLIC_KEY", "pk_test_sample", raising=False)
    client = TestClient(app)
    resp = client.get("/api/v1/checkout/config")
    data = resp.json()
    assert data["enabled"] is False
    assert data["public_key"] == ""

    # Case 2: Live key in development (disabled via safety guard)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development", raising=False)
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "sk_live_invalid_dev", raising=False)
    monkeypatch.setattr(settings, "PAYSTACK_PUBLIC_KEY", "pk_live_invalid_dev", raising=False)
    resp = client.get("/api/v1/checkout/config")
    data = resp.json()
    assert data["enabled"] is False
    assert data["public_key"] == ""


def test_webhook_fails_closed_with_503_when_environment_guard_violated(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config.settings import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "development", raising=False)
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "sk_live_forbidden", raising=False)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/checkout/webhook",
        content=b'{"event":"charge.success"}',
        headers={"x-paystack-signature": "dummy_sig"},
    )
    assert resp.status_code == 503
    assert "Payments not configured" in resp.json()["detail"]
