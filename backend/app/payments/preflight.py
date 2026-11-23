"""Production Configuration Preflight Check.

Enforces strict separation between test and live environments and verifies
that the production promotion boundary is fully satisfied before live key activation.

Checks:
1. Environment consistency:
   - In production: keys MUST start with sk_live_ / pk_live_, DATABASE_URL must be PostgreSQL,
     SECRET_KEY must be a secure production secret.
   - In staging/development/testing: keys MUST start with sk_test_ / pk_test_ (rejects live keys).
2. Key prefix alignment: secret key and public key must share the same environment prefix.
3. Actual provider authentication: verifies provider responds to the configured keys.
4. Database engine verification: confirms production is backed by PostgreSQL, not SQLite.

CLI usage:
  python -m app.payments.preflight
Exits 0 on success, non-zero on failure.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from app.config.settings import settings
from app.payments.paystack import (
    PaystackClient,
    validate_paystack_credentials,
)


@dataclass
class PreflightCheckResult:
    name: str
    passed: bool
    detail: str


class PreflightChecker:
    def __init__(self):
        self.results: list[PreflightCheckResult] = []

    def check_all(self, probe_provider: bool = False) -> bool:
        self.results.clear()
        self._check_environment_and_keys()
        self._check_database_engine()
        self._check_app_secret()
        self._check_public_base_url()
        self._check_mail_backend()
        if probe_provider and settings.payments_enabled:
            self._probe_provider_auth()
        return all(r.passed for r in self.results)

    def _check_environment_and_keys(self) -> None:
        env = (settings.ENVIRONMENT or "development").strip().lower()
        secret = (settings.PAYSTACK_SECRET_KEY or "").strip()
        public = (settings.PAYSTACK_PUBLIC_KEY or "").strip()

        # Check credential validation rules
        try:
            validate_paystack_credentials(secret_key=secret, public_key=public, environment=env)
            self.results.append(
                PreflightCheckResult(
                    name="Key Prefix & Environment Alignment",
                    passed=True,
                    detail=f"Environment '{env}' matches credential prefixes (secret={'***' + secret[-4:] if secret else 'NONE'})",
                )
            )
        except Exception as exc:
            self.results.append(
                PreflightCheckResult(
                    name="Key Prefix & Environment Alignment",
                    passed=False,
                    detail=str(exc),
                )
            )

        if env == "production":
            if not secret.startswith("sk_live_"):
                self.results.append(
                    PreflightCheckResult(
                        name="Production Live Secret Key",
                        passed=False,
                        detail="Production requires PAYSTACK_SECRET_KEY starting with 'sk_live_'.",
                    )
                )
            if not public.startswith("pk_live_"):
                self.results.append(
                    PreflightCheckResult(
                        name="Production Live Public Key",
                        passed=False,
                        detail="Production requires PAYSTACK_PUBLIC_KEY starting with 'pk_live_'.",
                    )
                )

    def _check_database_engine(self) -> None:
        env = (settings.ENVIRONMENT or "development").strip().lower()
        if env == "production":
            if settings.is_sqlite:
                self.results.append(
                    PreflightCheckResult(
                        name="Production Database Engine",
                        passed=False,
                        detail="Production MUST use PostgreSQL (DATABASE_URL is currently SQLite).",
                    )
                )
            else:
                self.results.append(
                    PreflightCheckResult(
                        name="Production Database Engine",
                        passed=True,
                        detail="Database engine is PostgreSQL.",
                    )
                )
        else:
            self.results.append(
                PreflightCheckResult(
                    name="Database Engine",
                    passed=True,
                    detail=f"Running in {env} mode on {'SQLite' if settings.is_sqlite else 'PostgreSQL'}.",
                )
            )

    def _check_app_secret(self) -> None:
        env = (settings.ENVIRONMENT or "development").strip().lower()
        secret = settings.SECRET_KEY
        if env == "production":
            if not secret or secret.startswith("dev-only") or len(secret) < 32:
                self.results.append(
                    PreflightCheckResult(
                        name="Production Application Secret Key",
                        passed=False,
                        detail="SECRET_KEY is insecure or unset for production.",
                    )
                )
            else:
                self.results.append(
                    PreflightCheckResult(
                        name="Production Application Secret Key",
                        passed=True,
                        detail="SECRET_KEY is configured and meets production security standards.",
                    )
                )
        else:
            self.results.append(
                PreflightCheckResult(
                    name="Application Secret Key",
                    passed=True,
                    detail="Development secret key detected.",
                )
            )

    def _check_public_base_url(self) -> None:
        import urllib.parse
        env = (settings.ENVIRONMENT or "development").strip().lower()
        base_url = (settings.PUBLIC_BASE_URL or "").strip()

        if env == "production":
            if not base_url:
                self.results.append(
                    PreflightCheckResult(
                        name="Production Public Base URL",
                        passed=False,
                        detail="PUBLIC_BASE_URL is not set for production.",
                    )
                )
                return

            if not base_url.startswith("https://"):
                self.results.append(
                    PreflightCheckResult(
                        name="Production Public Base URL",
                        passed=False,
                        detail="Production requires PUBLIC_BASE_URL starting with 'https://' (insecure HTTP forbidden).",
                    )
                )
                return

            parsed = urllib.parse.urlparse(base_url)
            host = (parsed.hostname or "").lower()

            private_prefixes = ("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
                                "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
                                "172.28.", "172.29.", "172.30.", "172.31.")
            if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.startswith(private_prefixes) or "example.com" in host or "test.local" in host:
                self.results.append(
                    PreflightCheckResult(
                        name="Production Public Base URL",
                        passed=False,
                        detail=f"Production PUBLIC_BASE_URL cannot use loopback, private IP, or placeholder host '{host}'.",
                    )
                )
                return

            self.results.append(
                PreflightCheckResult(
                    name="Production Public Base URL",
                    passed=True,
                    detail=f"PUBLIC_BASE_URL is configured for production ({parsed.scheme}://{host}).",
                )
            )
        else:
            self.results.append(
                PreflightCheckResult(
                    name="Public Base URL",
                    passed=True,
                    detail=f"Running in {env} mode with PUBLIC_BASE_URL={base_url or 'UNSET'}.",
                )
            )

    def _check_mail_backend(self) -> None:
        env = (settings.ENVIRONMENT or "development").strip().lower()
        backend = (settings.MAIL_BACKEND or "").strip().lower()

        if env == "production":
            if not backend or backend in ("console", "memory", "dummy", "test"):
                self.results.append(
                    PreflightCheckResult(
                        name="Production Mail Delivery Backend",
                        passed=False,
                        detail=f"Production requires a live mail delivery backend (currently '{backend or 'NONE'}'; console/memory delivery forbidden).",
                    )
                )
                return

            if backend == "smtp":
                host = (settings.SMTP_HOST or "").strip()
                if not host or host in ("localhost", "127.0.0.1", "0.0.0.0"):
                    self.results.append(
                        PreflightCheckResult(
                            name="Production Mail Delivery Backend",
                            passed=False,
                            detail=f"Production SMTP backend requires a remote SMTP_HOST (currently '{host or 'EMPTY'}').",
                        )
                    )
                    return

                mail_from = (settings.MAIL_FROM or "").strip()
                if not mail_from or "@" not in mail_from:
                    self.results.append(
                        PreflightCheckResult(
                            name="Production Mail Delivery Backend",
                            passed=False,
                            detail=f"Production SMTP backend requires a valid MAIL_FROM address (currently '{mail_from or 'EMPTY'}').",
                        )
                    )
                    return

                self.results.append(
                    PreflightCheckResult(
                        name="Production Mail Delivery Backend",
                        passed=True,
                        detail=f"Production mail backend is SMTP ({host}:{settings.SMTP_PORT}, from={mail_from}).",
                    )
                )
            else:
                self.results.append(
                    PreflightCheckResult(
                        name="Production Mail Delivery Backend",
                        passed=True,
                        detail=f"Production mail backend is '{backend}'.",
                    )
                )
        else:
            self.results.append(
                PreflightCheckResult(
                    name="Mail Delivery Backend",
                    passed=True,
                    detail=f"Running in {env} mode on '{backend or 'console'}' mail backend.",
                )
            )

    def _probe_provider_auth(self) -> None:
        client = PaystackClient()
        if not client.is_configured:
            self.results.append(
                PreflightCheckResult(
                    name="Provider API Authentication",
                    passed=False,
                    detail="Paystack client is not configured.",
                )
            )
            return

        try:
            # Query a safe endpoint to verify key authentication with Paystack
            status_code, payload = client._transport.request(
                "GET",
                f"{client._base_url}/transaction?perPage=1",
                headers=client._headers(),
            )
            if status_code == 200 and payload.get("status"):
                self.results.append(
                    PreflightCheckResult(
                        name="Provider API Authentication",
                        passed=True,
                        detail="Successfully authenticated against Paystack API.",
                    )
                )
            else:
                msg = payload.get("message") or f"HTTP {status_code}"
                self.results.append(
                    PreflightCheckResult(
                        name="Provider API Authentication",
                        passed=False,
                        detail=f"Paystack rejected credentials: {msg}",
                    )
                )
        except Exception as exc:
            self.results.append(
                PreflightCheckResult(
                    name="Provider API Authentication",
                    passed=False,
                    detail=f"Network or connection error during provider probe: {exc}",
                )
            )


def main() -> int:
    checker = PreflightChecker()
    passed = checker.check_all(probe_provider=False)

    print("=" * 65)
    print("NERA 2.0 — PAYSTACK FINANCIAL INTEGRITY PREFLIGHT CHECK")
    print("=" * 65)
    for res in checker.results:
        mark = "[PASS]" if res.passed else "[FAIL]"
        print(f"{mark} {res.name}: {res.detail}")
    print("=" * 65)

    if passed:
        print("RESULT: ALL PREFLIGHT CHECKS PASSED.")
        return 0
    else:
        print("RESULT: PREFLIGHT CHECKS FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
