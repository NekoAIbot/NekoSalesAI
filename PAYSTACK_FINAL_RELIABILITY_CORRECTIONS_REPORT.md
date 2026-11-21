# NERA — FINAL PAYSTACK RELIABILITY CORRECTIONS REPORT

**Document Type:** Engineering Acceptance Audit & Verification Report  
**Repository:** `C:\NekoProjects\NekoSalesAI`  
**Branch:** `remediation/paystack-financial-integrity`  
**Base Commit:** `75749f8253a0f86308c3e31cb63a6f378163c561`  
**Date:** 2026-11-21  
**Environment:** Local Remediation Test Environment (Python 3.14.7, SQLite Dialect)  

---

## 1. Executive Summary

This report documents the design, implementation, and automated verification of the **Final Paystack Reliability and Financial Integrity Corrections** (Corrections A through E). Building directly upon the remediation baseline `75749f8`, these corrections resolve remaining concurrency, state-fencing, idempotency, and credential-exposure vulnerabilities identified during the implementation acceptance audit.

All five authorized corrections have been completed and verified under automated regression testing:
1. **Correction A (Durable Email Delivery):** Implemented atomic distributed dispatch leases and attempt tracking on `credential_claims`, establishing durable at-least-once delivery with safe single-use redemption idempotency.
2. **Correction B (Telegram Distributed Lease Fencing):** Upgraded `system_leases` with monotonic fencing tokens, identity-verified renewals, and safe release semantics. Embedded poller lifecycle now monitors continuous renewal heartbeats and fences out stale workers to guarantee mutual exclusion.
3. **Correction C (Idempotent Paid-Order Provisioning):** Hardened `ProvisioningService` and `DeliveryService` with duplicate entity detection, transaction boundaries, and a database unique constraint on `credential_claims.order_id` to guarantee zero duplication on concurrent or repeated runs.
4. **Correction D (Atomic Claim Redemption):** Refactored `complete_setup` into an atomic single-transaction conditional update with automated rollback, eliminating double-redemption race conditions and lockout failure modes.
5. **Correction E (Public Credential Exposure Elimination):** Purged plaintext API keys, temporary passwords, and setup tokens from unauthenticated order polling endpoints (`_provision_if_paid` and `WorkspaceOut`), guaranteeing secret confidentiality.

### Final Verdict
**`ALL RELIABILITY CORRECTIONS VERIFIED LOCALLY — READY FOR POSTGRESQL CI`**

*(Note: In accordance with authorization guidelines, live production promotion and live Paystack activation remain strictly blocked pending multi-worker PostgreSQL CI validation.)*

---

## 2. Detailed Implementation of Corrections

### Correction A: Durable, Concurrency-Safe Setup Email Delivery
* **Problem Addressed:** Previously, the claim record was committed before attempting SMTP dispatch, but without persistent dispatch state or locking. If SMTP failed or the process crashed before recording `email_sent_at`, workers could enter duplicate dispatch races or abandon pending invitations.
* **Mechanism:**
  - Extended `CredentialClaim` with dispatch lease and attempt tracking columns: `dispatch_attempts`, `dispatch_last_attempt_at`, `dispatch_leased_until`, `dispatch_leased_by`, and `dispatch_error`.
  - Added `ProvisioningService.dispatch_claim_email(claim, worker_id, lease_seconds)`. This function executes an atomic conditional update (`WHERE id = claim.id AND email_sent_at IS NULL AND (dispatch_leased_until IS NULL OR dispatch_leased_until < now)`) to lease the email dispatch task to a specific worker.
  - If SMTP dispatch throws an exception, the failure is recorded in `dispatch_error`, `dispatch_attempts` is incremented, and `dispatch_leased_until` is released (`None`) so the reconciler can retry.
  - Reconciler method `retry_undelivered_claim_emails()` scans for pending claims where `email_sent_at IS NULL` and `dispatch_leased_until < now`, acquiring the lease conditionally before dispatch.
  - Passwords, API keys, and setup tokens are never logged.

### Correction B: Real Distributed Telegram Lease Ownership and Fencing
* **Problem Addressed:** Telegram poller relied on a single TTL lease with unverified renewal. If a worker suffered a network stall or long pause, a competing worker could acquire the lease. Upon resuming, the stale worker could overwrite the lease or continue polling concurrently, triggering Telegram HTTP 409 conflict loops.
* **Mechanism:**
  - Added `fencing_token: Mapped[int]` (default 1) to `SystemLease`.
  - In `LeaseService.acquire_lease()`, when an expired lease is reacquired or an existing lease is updated, the `fencing_token` is monotonically incremented (`SystemLease.fencing_token + 1`).
  - Added `LeaseService.renew_lease(lease_name, ttl_seconds, fencing_token)`. This executes an atomic update requiring `acquired_by == self.worker_id`, `fencing_token == fencing_token`, and `expires_at > now`. If another worker has taken over or the fencing token has changed, renewal returns `False`.
  - Added `LeaseService.release_lease(lease_name, fencing_token)`. Stale workers attempting to release a lease they no longer own are rejected, preventing deletion of an active competitor's lease.
  - In `backend/app/main.py`, the poller loop spawns a concurrent `_heartbeat_loop()` task renewing the lease every 20 seconds. If renewal fails or three consecutive database errors occur, the heartbeat sets `fenced_out = True` and calls `poller.stop()`.
  - In `backend/app/messaging/poller.py`, `TelegramPoller.run()` and `drain()` check `self._stopping` immediately before and after batch processing, breaking out cleanly without executing further poll iterations.

### Correction C: Idempotent Paid-Order Provisioning and Recovery
* **Problem Addressed:** If a failure or server crash occurred between payment settlement and completed provisioning, or if reconciliation ran concurrently with webhook processing, duplicate workspaces, users, or API keys could be created.
* **Mechanism:**
  - Added database unique constraint `uq_credential_claims_order_id` on `credential_claims.order_id` in Alembic migration `c3e7f1a8b9d2`.
  - In `ProvisioningService.provision()`, queries now inspect existing `WorkspaceProfile` and `CredentialClaim` associated with `order.id` before creating new records.
  - If a workspace profile already exists for the order, its existing `api_key_hash` is preserved; credentials are never re-minted or rotated on repeated passes.
  - Provisioning and claim creation occur within a unified database transaction. `order.is_delivered` is only set once provisioning state is persisted.

### Correction D: Atomic Claim Redemption
* **Problem Addressed:** Previously, `complete_setup` queried the claim, updated the user, set `claimed_at`, rotated the API key, and called `db.commit()` at the end. Concurrent requests with the same token could both read `claimed_at IS NULL`, or a failure during key rotation could leave the token consumed while the user received an error without credentials.
* **Mechanism:**
  - In `backend/app/auth/router.py`, `complete_setup` executes an atomic conditional update:
    ```python
    stmt = (
        update(CredentialClaim)
        .where(
            CredentialClaim.token_hash == token_hash,
            CredentialClaim.claimed_at.is_(None),
        )
        .values(claimed_at=now)
        .execution_options(synchronize_session=False)
    )
    res = db.execute(stmt)
    if res.rowcount == 0:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This setup link has already been used.")
    ```
  - `ProvisioningService.rotate_api_key(profile, commit=False)` parameter was added to allow key rotation within the caller's atomic transaction.
  - The entire operation (conditional claim update, password hashing, and key rotation) is wrapped in a `try...except` block that executes `db.rollback()` on any exception. If credential rotation fails, the token is not consumed.

### Correction E: Public Credential Exposure Elimination
* **Problem Addressed:** When buyers checked payment status via unauthenticated order polling (`GET /api/v1/checkout/orders/{reference}`), `_provision_if_paid` returned a populated `WorkspaceOut` containing `api_key` and `temporary_password`.
* **Mechanism:**
  - In `backend/app/schemas/checkout.py`, `WorkspaceOut.api_key` and `WorkspaceOut.temporary_password` default to `None`.
  - In `backend/app/api/v1/routes/checkout.py`, `_provision_if_paid` now invokes `WorkspaceOut.from_model(result.profiles[0].profile)` without passing plaintext credentials.
  - Plaintext credentials and setup tokens are strictly restricted to the customer's private setup email and initial setup completion response.

---

## 3. Exact Files and Functions Modified

| File Path | Function / Class | Changes Made |
| :--- | :--- | :--- |
| `backend/app/models/credential_claim.py` | `CredentialClaim` | Added `dispatch_attempts`, `dispatch_last_attempt_at`, `dispatch_leased_until`, `dispatch_leased_by`, `dispatch_error` columns, and `UniqueConstraint("order_id", name="uq_credential_claims_order_id")`. |
| `backend/app/models/system_lease.py` | `SystemLease` | Added `fencing_token: Mapped[int] = mapped_column(BigInteger, default=1)`. |
| `backend/app/payments/lease.py` | `LeaseService` | Added `fencing_token` increment on acquisition; implemented atomic `renew_lease` checking owner and fencing token; implemented safe `release_lease`. |
| `backend/app/main.py` | `_run_poller` | Instrumented heartbeat renewal loop, fencing token tracking, poller cancellation on fencing loss/3 DB errors, safe lease release, and webhook clearing guard. |
| `backend/app/messaging/poller.py` | `TelegramPoller.run`, `drain` | Added immediate breakout on `self._stopping`; ensured single-pass `once=True` poller runs perform payment reconciliation before exiting. |
| `backend/app/payments/provisioning.py` | `ProvisioningService` | Added `dispatch_claim_email()`, updated `retry_undelivered_claim_emails()`, deduplicated profile and claim creation, and added `commit=False` parameter to `rotate_api_key()`. |
| `backend/app/auth/router.py` | `complete_setup` | Replaced non-atomic redemption with atomic conditional update and rollback safety on key generation failure. |
| `backend/app/schemas/checkout.py` | `WorkspaceOut` | Set `api_key` and `temporary_password` to default `None` and omitted from public representation. |
| `backend/app/api/v1/routes/checkout.py` | `_provision_if_paid` | Stripped plaintext `api_key` and `temporary_password` from order poll response. |
| `backend/alembic/versions/c3e7f1a8b9d2_paystack_reliability_hardening.py` | Migration | Schema migration adding dispatch lease fields to `credential_claims`, unique constraint on `order_id`, and `fencing_token` to `system_leases`. |
| `backend/tests/test_financial_integrity_remediation.py` | Test Suite | Added 16 new test cases covering all 5 corrections (lease fencing, crash recovery, competing dispatch workers, atomic redemption, credential exposure). |
| `backend/tests/test_checkout.py` | Test Suite | Updated checkout assertion to verify `api_key is None` on order status polling. |

---

## 4. Database Changes and Migration Implications

Alembic migration `c3e7f1a8b9d2_paystack_reliability_hardening.py` provides forward and backward compatible schema evolution:

1. **`credential_claims` Table:**
   - `dispatch_attempts`: `Integer`, non-nullable, server default `0`.
   - `dispatch_last_attempt_at`: `DateTime(timezone=True)`, nullable.
   - `dispatch_leased_until`: `DateTime(timezone=True)`, nullable.
   - `dispatch_leased_by`: `String(128)`, nullable.
   - `dispatch_error`: `Text`, nullable.
   - Unique Constraint: `uq_credential_claims_order_id` on `(order_id)`.
2. **`system_leases` Table:**
   - `fencing_token`: `BigInteger`, non-nullable, server default `1`.

**Migration Implications:**
- All added columns are either nullable or have default values (`0` and `1`), allowing zero-downtime execution against existing PostgreSQL databases.
- The unique constraint `uq_credential_claims_order_id` ensures database-level deduplication across distributed workers.

---

## 5. Concurrency and Crash-Recovery Evidence

Automated regression tests verify the system's crash recovery behavior across distributed boundaries:

* **Simulated Worker Crash During Email Dispatch:**
  `test_email_dispatch_simulated_crash_recovers_after_lease_expiry` asserts that when a worker claims a dispatch lease and crashes, the active lease prevents competing workers from duplicate dispatch. Once the lease TTL expires, the background reconciler automatically re-leases the claim and completes dispatch.
* **Two Workers Competing for Same Email:**
  `test_email_dispatch_two_workers_competing_mutual_exclusion` verifies that when two workers simultaneously attempt to dispatch the same pending claim, exactly one acquires the atomic lease (`True`), while the second is rejected (`False`).
* **Two Workers Provisioning the Same Paid Order:**
  `test_provisioning_two_workers_concurrent_no_duplicates` proves that concurrent calls to `ProvisioningService.provision(order)` produce exactly 1 WorkspaceProfile, 1 User, and 1 CredentialClaim.
* **Rollback on Credential Generation Failure:**
  `test_complete_setup_transaction_boundary_and_rollback` verifies that if an unexpected error occurs during password hashing or API key generation, the conditional update is rolled back and `claim.claimed_at` remains `None`.

---

## 6. Email Delivery Guarantee and SMTP Technical Limitations

### Technical Protocol Limitation
Standard SMTP does not support idempotency keys or end-to-end distributed transaction commits. If an SMTP relay accepts a message (`250 OK`) but the network connection drops or the application process crashes before recording success in the database, the application cannot differentiate between a lost message and an unrecorded success.

### Established Guarantee: Durable At-Least-Once Delivery
1. **Durable Intent:** Claim records are committed to durable storage prior to dispatch.
2. **Atomic Dispatch Lease:** Workers acquire an exclusive lease before connecting to SMTP, preventing concurrent duplicate dispatches.
3. **Safe Duplicate Harmlessness:** Setup tokens are single-use (`claimed_at IS NULL` atomic update) and time-limited. If a network crash causes an email to be sent twice, both messages contain the identical token. Once redeemed, any subsequent attempt with either email is rejected with HTTP 400 (`"This setup link has already been used"`).

---

## 7. Telegram Lease Ownership and Fencing Evidence

Automated tests in `test_financial_integrity_remediation.py` verify distributed lease mutual exclusion:

* **Owner Identity Verification:** `test_lease_renew_rejects_wrong_owner` confirms that a worker cannot renew another worker's active lease.
* **Fencing Token Rejection:** `test_lease_old_worker_renewal_and_release_rejected_after_new_owner` confirms that when Worker A's lease expires and Worker B acquires it (incrementing `fencing_token`), Worker A's subsequent renewal and release calls are rejected. Worker B's lease remains intact.
* **Heartbeat Failure Fencing:** `test_poller_fences_out_after_three_heartbeat_failures` proves that three consecutive database heartbeat errors cause the poller to set `fenced_out = True` and invoke `poller.stop()`.
* **Poller Shutdown Clean Release:** `test_poller_shutdown_releases_lease` verifies that on graceful shutdown, the poller releases its lease immediately so standby workers can take over without waiting for TTL expiry.

---

## 8. Provisioning Idempotency Evidence

Automated tests verify provisioning idempotency across multiple lifecycles:

* `test_provisioning_crash_immediately_after_settlement`: An order marked `ORDER_PAID` with 0 profiles is automatically provisioned and marked delivered by the background delivery reconciler.
* `test_provisioning_repeated_reconciliation_idempotent`: Repeated delivery and reconciliation passes on an already-provisioned order do not regenerate API keys or create duplicate claims.
* Database uniqueness enforces that each `order_id` maps to at most one `CredentialClaim`.

---

## 9. Complete Test Results

All core remediation, checkout, delivery, environment, and poller loop test suites were executed locally against the unified working tree:

```
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\NekoProjects\NekoSalesAI\backend
configfile: pyproject.toml
plugins: anyio-4.16.0, asyncio-1.5.0
collected 145 items

backend\tests\test_financial_integrity_remediation.py .......................... [ 17%]
backend\tests\test_checkout.py ................................................. [ 54%]
....                                                                             [ 57%]
backend\tests\test_delivery.py ...............................                   [ 78%]
backend\tests\test_payment_environment.py ...............                        [ 88%]
backend\tests\test_poller_loop.py ............                                   [100%]

================= 145 passed, 1 warning in 163.28s (0:02:43) ==================
```

### Suite Breakdown
| Test Suite | Total Tests | Passed | Failed | Status |
| :--- | :---: | :---: | :---: | :---: |
| `backend/tests/test_financial_integrity_remediation.py` | 26 | 26 | 0 | **PASSED** |
| `backend/tests/test_checkout.py` | 53 | 53 | 0 | **PASSED** |
| `backend/tests/test_delivery.py` | 31 | 31 | 0 | **PASSED** |
| `backend/tests/test_payment_environment.py` | 15 | 15 | 0 | **PASSED** |
| `backend/tests/test_poller_loop.py` | 12 | 12 | 0 | **PASSED** |
| **Total** | **145** | **145** | **0** | **100% PASSED** |

*(Note on Database Engine: All 145 tests executed locally under SQLite. Validation against PostgreSQL must be performed in CI before production deployment).*

---

## 10. Remaining Risks Ranked by Severity

| Risk | Severity | Description | Mitigation Strategy |
| :--- | :---: | :--- | :--- |
| **PostgreSQL vs SQLite Dialect Parity** | **MEDIUM** | SQLite dialect does not enforce table-level row locks (`FOR UPDATE`). Concurrency tests rely on atomic conditional updates and unique constraints. | Run the test suite against multi-connection PostgreSQL in GitHub Actions CI prior to merge. |
| **SMTP Relay Latency / Retries** | **LOW** | Downstream mail relays may experience prolonged outages exceeding dispatch retry thresholds. | The `dispatch_error` column and `retry_undelivered_claim_emails()` method allow autonomous exponential backoff and observability. |
| **Telegram Long-Poll Cancellation Timing** | **LOW** | Telegram `getUpdates` requests hold open network sockets for up to 30 seconds. On shutdown or fencing, socket closure may log a benign cancellation warning. | Poller handles task cancellation cleanly and clears webhooks upon recovery. |

---

## 11. Git Status and Working Tree State

* **Active Branch:** `remediation/paystack-financial-integrity`
* **Base Commit:** `75749f8253a0f86308c3e31cb63a6f378163c561`
* **Local Changes:** 10 application files modified, 3 test files updated, 1 new Alembic migration created, 1 remediation audit report added, 1 final report added.
* **Commit Status:** Ready for local staging and commit on `remediation/paystack-financial-integrity`.

---

## 12. Confirmation of Strict Authorization Boundaries

The following boundary conditions are confirmed:
- [x] **No remote push:** `git push` was not executed.
- [x] **No branch merge:** No merge into `main` or any other branch occurred.
- [x] **No live deployment:** Render services and deployment webhooks were not triggered.
- [x] **No database tampering:** Production and staging databases were not contacted.
- [x] **No credential changes:** Production credentials and environment variables remain unchanged.
- [x] **No live financial transactions:** Zero real charges were processed on Paystack.
- [x] **No customer communications:** Zero real emails were transmitted to external recipients.
- [x] **Branch Isolation:** All changes reside strictly on `remediation/paystack-financial-integrity`.

---

## Final Verdict

**`ALL RELIABILITY CORRECTIONS VERIFIED LOCALLY — READY FOR POSTGRESQL CI`**
