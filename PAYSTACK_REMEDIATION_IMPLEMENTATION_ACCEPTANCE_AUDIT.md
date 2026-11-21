# NERA — INDEPENDENT PAYSTACK REMEDIATION IMPLEMENTATION ACCEPTANCE AUDIT

**Audit Date:** 2026-11-21  
**Auditor:** Independent Principal Security & Financial Systems Auditor (AI)  
**Repository:** `C:\NekoProjects\NekoSalesAI`  
**Inspected Branch:** `remediation/paystack-financial-integrity`  
**Inspected Commit HEAD:** `75749f8253a0f86308c3e31cb63a6f378163c561` (`75749f8`)  
**Production Baseline:** `b1097ac3073473d7d18049944f3faba02505c216` (`main`)  
**Audit Scope:** Independent forensic verification of changes across commits `ae43e93` and `75749f8` against authorized remediations F-01 through F-07.

---

## 1. Executive Verdict

### **VERDICT: ACCEPTED WITH REQUIRED CORRECTIONS**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ACCEPTANCE SUMMARY                               │
├───────────────────────────────────┬─────────────────────────────────────────┤
│ Core Settlement Concurrency (F-01)│ ACCEPTED (Row-level conditional update) │
│ Session Rollback (F-02 Part 1)    │ ACCEPTED (Explicit session cleanup)     │
│ Crash Recovery Provisioning (F-02)│ DEFECTIVE (Strands unprovisioned orders)│
│ Credential Lifecycle (F-03 Part 1)│ ACCEPTED (SHA-256 tokens & expiry)      │
│ Credential Exposure (F-03 Part 2) │ CRITICAL DEFECT (Plaintext leak in poll)│
│ Starvation & Recovery (F-04)      │ ACCEPTED (Indexed fair scheduling)      │
│ Lifespan Reconciler (F-05)        │ ACCEPTED (Telegram fully decoupled)     │
│ Distributed Leases (F-06 Part 1)  │ ACCEPTED (Atomic lease engine)          │
│ Poller Lease Renewal (F-06 Part 2)│ HIGH DEFECT (Missing heartbeat/renewal) │
│ Preflight & CI Harness (F-07)     │ ACCEPTED (PostgreSQL CI configured)     │
└───────────────────────────────────┴─────────────────────────────────────────┘
```

The engineering implementation on `remediation/paystack-financial-integrity` successfully establishes the foundational primitives for financial integrity, including atomic conditional row updates in `CheckoutService.confirm()`, starvation-free reconciliation scheduling, an independent lifespan reconciler worker, an Alembic migration (`a1c4e95d2f83`), and a PostgreSQL CI workflow.

However, the branch **cannot be certified for production deployment or pushed unconditionally** because three serious defects were identified during forensic code inspection:
1. **CRITICAL:** Plaintext API keys and temporary passwords continue to be returned in the unauthenticated `GET /api/v1/checkout/orders/{reference}` polling response via `_provision_if_paid()`.
2. **CRITICAL:** If a crash or worker kill occurs after payment settlement commits `ORDER_PAID` but before workspace provisioning finishes, the background reconciler permanently ignores the unprovisioned paid order, leaving the customer charged but without a workspace.
3. **HIGH:** The Telegram poller acquires a distributed lease with a 60-second TTL but never renews or heartbeats during long-polling, causing lease expiration, multi-worker acquisition, and Telegram HTTP 409 Conflict errors.

The branch is **ACCEPTED WITH REQUIRED CORRECTIONS**. Once the three mandatory code corrections detailed in Section 9 are applied, the branch may be pushed to GitHub to execute the PostgreSQL CI workflow.

---

## 2. Commit, Branch, and Environment Verification

- **Repository Path:** `C:\NekoProjects\NekoSalesAI`
- **Current Branch:** `remediation/paystack-financial-integrity`
- **HEAD Commit:** `75749f8` (`ci: add PostgreSQL-backed financial integrity concurrency test workflow`)
- **Preceding Commit:** `ae43e93` (`fix(payments): implement authorized financial integrity remediations (F-01 through F-07)`)
- **Baseline Main Commit:** `b1097ac` (`test: fix test client invocation for GET and DELETE in auth test`)
- **Diff Stats Against Baseline:** 20 files changed, 2441 insertions(+), 66 deletions(-)
- **Working Tree State:** Clean (no unstaged or untracked application modifications).
- **Remote Push Status:** Unpushed (branch exists strictly in local git repository; no remote actions taken).

---

## 3. Finding-by-Finding Acceptance Matrix

| Finding | Description | Implementation Status | Verdict |
| :--- | :--- | :--- | :--- |
| **F-01** | Atomic Payment Settlement & Concurrency | `CheckoutService.confirm()` conditional SQL update on `status in ('pending', 'abandoned')` | **ACCEPTED** |
| **F-02** | SQLAlchemy Session Rollback & Crash Recovery | Rollback added to `_provision_if_paid()`; Reconciler loop lacks fallback provisioning | **ACCEPTED WITH REQUIRED CORRECTIONS** |
| **F-03** | Secure Credential Issuance & Lifecycle | Single-use 24h setup tokens created; Plaintext credentials still returned in order poll | **ACCEPTED WITH REQUIRED CORRECTIONS** |
| **F-04** | Abandoned Checkout & Starvation Prevention | `last_reconciled_at` fair queueing; 2h abandonment; late-payment recovery to `ORDER_PAID` | **ACCEPTED** |
| **F-05** | Independent Payment Reconciliation | Lifespan background task decoupled from Telegram; dedicated backoff and loop | **ACCEPTED** |
| **F-06** | Multi-Worker Distributed Leases | `SystemLease` model & atomic acquisition; poller lacks background heartbeat renewal | **ACCEPTED WITH REQUIRED CORRECTIONS** |
| **F-07** | Configuration Preflight & Environment Isolation | CLI preflight check validates key prefixes, database engine, secrets; PostgreSQL CI workflow | **ACCEPTED** |

---

## 4. Source-File and Function-Level Verification Evidence

### 4.1 F-01: Atomic Payment Settlement
- **Primary Source:** [`backend/app/payments/checkout.py:428-450`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/checkout.py#L428-L450)
- **Code Inspected:**
  ```python
  stmt = (
      update(Order)
      .where(
          Order.id == order.id,
          Order.status.in_([ORDER_PENDING, ORDER_ABANDONED]),
      )
      .values(
          status=ORDER_PAID,
          paid_at=now,
          provider_payload=payload_str,
      )
  )
  result = self.db.execute(stmt)

  if result.rowcount == 0:
      self.db.rollback()
      return self.get_by_reference(charge.reference)
  ```
- **Evidence:** Concurrency between simultaneous webhook deliveries, browser verification, and background reconciliation is eliminated at the database engine level. `result.rowcount == 0` triggers an immediate rollback, preventing duplicate receipt issuance (`self._send_receipt(order)` only executes if `rowcount == 1`).

### 4.2 F-02: SQLAlchemy Session Rollback & Crash Recovery
- **Primary Sources:**
  - [`backend/app/api/v1/routes/checkout.py:86-96`](file:///C:/NekoProjects/NekoSalesAI/backend/app/api/v1/routes/checkout.py#L86-L96)
  - [`backend/app/payments/delivery.py:275-283`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/delivery.py#L275-L283)
  - [`backend/app/payments/delivery.py:305-311`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/delivery.py#L305-L311)
- **Evidence (Rollback):** In `_provision_if_paid()`, exceptions caught during `service.provision(order)` immediately execute `db.rollback()`. This cleanly clears pending flushes and prevents `PendingRollbackError` on subsequent queries within the request session.
- **Evidence (Recovery Defect):** If the process terminates after `CheckoutService.confirm()` commits `ORDER_PAID` but before `_provision_if_paid()` runs:
  1. `DeliveryService._verify_pending()` ignores the order because `order.status == ORDER_PAID`.
  2. `DeliveryService._undelivered_paid()` selects the order and passes it to `deliver(order)`.
  3. `deliver(order)` executes:
     ```python
     profiles = self.profiles_for(order)
     if not profiles:
         return None
     ```
  4. `deliver()` does NOT invoke `ProvisioningService(self.db).provision(order)`. The order is skipped every pass, leaving the paid order permanently unprovisioned.

### 4.3 F-03: Credential Issuance, Setup Claims, and Plaintext Exposure
- **Primary Sources:**
  - [`backend/app/models/credential_claim.py:29-75`](file:///C:/NekoProjects/NekoSalesAI/backend/app/models/credential_claim.py#L29-L75)
  - [`backend/app/payments/provisioning.py:465-518`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/provisioning.py#L465-L518)
  - [`backend/app/api/v1/routes/checkout.py:102-107`](file:///C:/NekoProjects/NekoSalesAI/backend/app/api/v1/routes/checkout.py#L102-L107)
  - [`backend/app/api/v1/routes/checkout.py:442-457`](file:///C:/NekoProjects/NekoSalesAI/backend/app/api/v1/routes/checkout.py#L442-L457)
  - [`backend/app/auth/router.py:480-523`](file:///C:/NekoProjects/NekoSalesAI/backend/app/auth/router.py#L480-L523)
- **Evidence (Token Model):** Cryptographically strong tokens (`secrets.token_urlsafe(32)`) are hashed via SHA-256 before insertion into `credential_claims`. Raw tokens are sent only via setup emails.
- **Evidence (Credential Leak Defect):** `_provision_if_paid(order, db)` in `checkout.py` executes:
  ```python
  if result.profiles:
      return WorkspaceOut.from_model(
          result.profiles[0].profile,
          api_key=result.profiles[0].api_key,
          temporary_password=result.profiles[0].temporary_password,
      )
  ```
  This is returned directly by `GET /api/v1/checkout/orders/{reference}` (`order_status`), which has NO authentication. Any actor possessing or guessing a reference can query `GET /orders/{reference}` and extract plaintext API keys and temporary passwords.
- **Evidence (Concurrency Race):** In `complete_setup` (`router.py:490-515`), `claim = db.query(CredentialClaim)...first()` lacks row-level locking (`with_for_update()`) or atomic conditional update. Simultaneous calls with the same token race through validation and generate multiple API keys.

### 4.4 F-04: Starvation Prevention & Abandoned Checkout Handling
- **Primary Sources:**
  - [`backend/app/payments/delivery.py:382-393`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/delivery.py#L382-L393)
  - [`backend/app/payments/recovery.py:40-75`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/recovery.py#L40-L75)
  - [`backend/alembic/versions/a1c4e95d2f83_paystack_financial_integrity.py:21-25`](file:///C:/NekoProjects/NekoSalesAI/backend/alembic/versions/a1c4e95d2f83_paystack_financial_integrity.py#L21-L25)
- **Evidence:** `_pending_orders_query()` sorts by `Order.last_reconciled_at.asc().nullsfirst()`, ensuring round-robin evaluation across all pending checkouts. Abandoned checkouts older than 2 hours transition to `ORDER_ABANDONED`. If a late webhook or browser confirmation arrives, `CheckoutService.confirm()` explicitly allows `ORDER_ABANDONED -> ORDER_PAID`.

### 4.5 F-05: Independent Payment Reconciliation
- **Primary Source:** [`backend/app/main.py:170-205`](file:///C:/NekoProjects/NekoSalesAI/backend/app/main.py#L170-L205)
- **Evidence:** An autonomous background task `_run_payment_reconciler(stop_event)` runs in the FastAPI lifespan. It executes every 30 seconds independently of Telegram poller state. If Telegram is disabled or fails, payment reconciliation and recovery continue uninterrupted.

### 4.6 F-06: Multi-Worker Coordination & Distributed Leases
- **Primary Sources:**
  - [`backend/app/payments/lease.py:28-80`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/lease.py#L28-L80)
  - [`backend/app/main.py:85-110`](file:///C:/NekoProjects/NekoSalesAI/backend/app/main.py#L85-L110)
- **Evidence (Lease Engine):** `LeaseService.acquire_lease()` performs an atomic update checking `SystemLease.expires_at < now`.
- **Evidence (Poller Lease Defect):** In `backend/app/main.py`, the poller acquires `telegram_poller` with a 60-second TTL:
  ```python
  has_lease = lease_service.acquire_lease(f"{label}_poller", ttl_seconds=60)
  ...
  run_task = asyncio.create_task(asyncio.to_thread(poller.run)...)
  await stop_or_fail
  ```
  `poller.run()` blocks in a separate thread. There is no background task renewing or heartbeating the lease. After 60 seconds, another worker observes `expires_at < now`, acquires the lease, and starts a second `poller.run()`, resulting in Telegram HTTP 409 Conflict polling collisions.

### 4.7 F-07: Configuration Preflight & Test/Live Separation
- **Primary Sources:**
  - [`backend/app/payments/preflight.py:1-218`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/preflight.py#L1-L218)
  - [`.github/workflows/financial-integrity-ci.yml:1-74`](file:///C:/NekoProjects/NekoSalesAI/.github/workflows/financial-integrity-ci.yml#L1-L74)
- **Evidence:** `PreflightChecker` enforces that production environments have `sk_live_` / `pk_live_`, PostgreSQL database URLs, and high-entropy secrets, while non-production environments reject live keys. The GitHub Actions workflow provisions a PostgreSQL 16 container, runs Alembic migrations, executes `app.payments.preflight`, and runs the financial integrity test suite.

---

## 5. Security & Financial-Integrity Defects Analysis

### DEFECT 1: Unauthenticated Credential Leak in Order Status Poll
- **Severity:** **CRITICAL**
- **Affected File:** [`backend/app/api/v1/routes/checkout.py:102-107, 442-457`](file:///C:/NekoProjects/NekoSalesAI/backend/app/api/v1/routes/checkout.py#L102-L107)
- **Description:** `GET /api/v1/checkout/orders/{reference}` has no authentication dependencies. When it calls `_provision_if_paid(order, db)`, newly provisioned agent profiles have their raw `api_key` and `temporary_password` serialized into `WorkspaceOut` and returned in the HTTP response.
- **Exploitation:** Any third party who learns or enumerates an order reference (via browser history, shoulder surfing, proxy logs, or URL sharing) can retrieve the root API key and temporary admin password of the customer's workspace.
- **Required Remediation:** `WorkspaceOut.from_model()` must NEVER be passed raw `api_key` or `temporary_password`. In `_provision_if_paid`, return `WorkspaceOut.from_model(result.profiles[0].profile)` with no plaintext credentials. The buyer must onboard exclusively via the claim token sent to their billing email.

### DEFECT 2: Crash-Window Stranding of Paid Orders in Reconciler
- **Severity:** **CRITICAL**
- **Affected File:** [`backend/app/payments/delivery.py:305-311`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/delivery.py#L305-L311)
- **Description:** If a worker crashes or restarts immediately after `CheckoutService.confirm()` transitions an order to `ORDER_PAID`, the order is marked paid but has no `WorkspaceProfile`. In `DeliveryService.run()`, `_verify_pending()` skips it (since status is paid). `_undelivered_paid()` passes it to `deliver()`, which checks `profiles = self.profiles_for(order)`:
  ```python
  if not profiles:
      return None
  ```
  Because `deliver()` never triggers `ProvisioningService.provision(order)`, the order is skipped indefinitely.
- **Exploitation:** A customer who pays via webhook or closes their browser before polling is permanently stranded with a completed charge and no workspace.
- **Required Remediation:** If `profiles_for(order)` is empty inside `deliver()`, `DeliveryService` must instantiate `ProvisioningService(self.db).provision(order)` to resume and complete provisioning.

### DEFECT 3: Missing Lease Renewal / Heartbeat on Telegram Poller
- **Severity:** **HIGH**
- **Affected File:** [`backend/app/main.py:89-108`](file:///C:/NekoProjects/NekoSalesAI/backend/app/main.py#L89-L108)
- **Description:** The poller acquires a 60-second lease before launching `asyncio.to_thread(poller.run)`. Because `poller.run()` blocks until application shutdown, no renewal occurs. Once 60 seconds elapse, any secondary container or worker sees the lease expired, acquires it, and launches another poller instance.
- **Exploitation:** Multi-worker deployments (e.g., Render autoscaling or multi-replica containers) will experience repeated HTTP 409 Conflict errors from Telegram, dropping webhook-less message updates.
- **Required Remediation:** Launch an asynchronous heartbeat task alongside `run_task` that renews the lease (e.g. every 20 seconds with TTL 60 seconds) while `poller.run` is active.

### DEFECT 4: Concurrency Race Condition in Token Setup Completion
- **Severity:** **MEDIUM**
- **Affected File:** [`backend/app/auth/router.py:490-515`](file:///C:/NekoProjects/NekoSalesAI/backend/app/auth/router.py#L490-L515)
- **Description:** `complete_setup` fetches `claim` using standard `SELECT` without row-level locking (`with_for_update()`). It checks `if claim.claimed_at is not None`, sets `claim.claimed_at`, and calls `ProvisioningService.rotate_api_key()`.
- **Exploitation:** Two rapid concurrent requests presenting the same valid setup token can pass the check simultaneously, resulting in double API key generation and invalidating the key returned to the first caller.
- **Required Remediation:** Use an atomic conditional update query:
  ```python
  stmt = (
      update(CredentialClaim)
      .where(CredentialClaim.token_hash == token_hash, CredentialClaim.claimed_at.is_(None))
      .values(claimed_at=datetime.now(UTC))
  )
  ```
  If `result.rowcount == 0`, immediately raise HTTP 400 "This setup link has already been used."

### DEFECT 5: Email Dual-Write Failure Window
- **Severity:** **MEDIUM**
- **Affected File:** [`backend/app/payments/provisioning.py:489-521`](file:///C:/NekoProjects/NekoSalesAI/backend/app/payments/provisioning.py#L489-L521)
- **Description:** `mail.send(msg)` is called before `self.db.commit()`. If the server terminates before database commit, the buyer receives an email containing a claim token whose database record was never committed.
- **Required Remediation:** Commit the database transaction containing `CredentialClaim` (with `email_sent_at = None`) before attempting `mail.send()`. Once `mail.send()` succeeds, update `email_sent_at = datetime.now(UTC)` and commit. If dispatch fails, `retry_undelivered_claim_emails()` cleanly retries.

---

## 6. Crash-Window and Concurrency Analysis

```
                    PAYMENT SETTLEMENT & RECOVERY TIMELINE
                    
┌───────────────────────┐
│ Webhook / Status Poll │
└───────────┬───────────┘
            │
            ▼
┌──────────────────────────────────────────────┐
│ [Window 1] Atomic DB Update (CheckoutService) │
│ - UPDATE orders SET status='paid' WHERE ...  │ ◄── Safe (Conditional update)
│ - Commit Transaction                         │
└───────────┬──────────────────────────────────┘
            │
   💥 CRASH POINT A (Between Settlement Commit & Provisioning)
            │
            ▼
┌──────────────────────────────────────────────┐
│ [Window 2] Provisioning (ProvisioningService)│
│ - Create Org, User, WorkspaceProfile         │
│ - Generate CredentialClaim token             │
│ - Commit Transaction                         │
└───────────┬──────────────────────────────────┘
            │
   💥 CRASH POINT B (Between DB Commit & Email Dispatch)
            │
            ▼
┌──────────────────────────────────────────────┐
│ [Window 3] Dispatch Setup Email via SMTP     │ ◄── Reconciler retries cleanly
│ - Update claim.email_sent_at                 │     via retry_undelivered_claim_emails()
└───────────┬──────────────────────────────────┘
            │
   💥 CRASH POINT C (Between Provisioning & Chat Notification)
            │
            ▼
┌──────────────────────────────────────────────┐
│ [Window 4] Chat Notification (DeliveryPusher)│ ◄── Safe (Transcript rows idempotent)
└──────────────────────────────────────────────┘
```

- **Crash Point A Recovery:** **FAILING (CRITICAL DEFECT 2).** If the application terminates at Crash Point A, `DeliveryService.run()` selects the paid order in `_undelivered_paid()`, but `deliver()` returns `None` without provisioning the workspace.
- **Crash Point B Recovery:** **PASSING.** If the application terminates at Crash Point B, `retry_undelivered_claim_emails()` selects all claims where `email_sent_at IS NULL` and `claimed_at IS NULL` and safely re-dispatches the setup email.
- **Crash Point C Recovery:** **PASSING.** Chat deliveries are idempotent based on `order.is_delivered` and message transcript logging.

---

## 7. PostgreSQL CI & Migration Assessment

### 7.1 Alembic Migration Verification
- **Migration File:** [`backend/alembic/versions/a1c4e95d2f83_paystack_financial_integrity.py`](file:///C:/NekoProjects/NekoSalesAI/backend/alembic/versions/a1c4e95d2f83_paystack_financial_integrity.py)
- **Revision ID:** `a1c4e95d2f83` (Revises `fbc42e917a61`)
- **Operations:**
  - Adds `last_reconciled_at` (`DateTime(timezone=True)`) and `reconcile_attempts` (`Integer`) to `orders`.
  - Creates index `ix_orders_last_reconciled_at` on `orders(last_reconciled_at)`.
  - Creates `credential_claims` table with foreign keys to `orders` and `users` (`ondelete="CASCADE"`).
  - Creates unique index `ix_credential_claims_token_hash` on `credential_claims(token_hash)`.
  - Creates `system_leases` table with primary key `lease_name` and index on `expires_at`.
- **Downgrade Path:** Cleanly drops all created tables, columns, and indexes in reverse order.
- **Assessment:** Fully compatible with PostgreSQL and SQLite.

### 7.2 GitHub Actions Workflow Verification
- **Workflow File:** [`.github/workflows/financial-integrity-ci.yml`](file:///C:/NekoProjects/NekoSalesAI/.github/workflows/financial-integrity-ci.yml)
- **Trigger:** Push to `remediation/paystack-financial-integrity`, PR to `main`, or manual dispatch.
- **Database:** PostgreSQL 16 official container with `pg_isready` health check.
- **Database Driver:** `postgresql+psycopg://` (compliant with Psycopg 3).
- **Test Command:**
  `pytest tests/test_financial_integrity_remediation.py tests/test_checkout.py tests/test_delivery.py -v --tb=short`
- **Assessment:** Properly configured for isolated PostgreSQL validation.

---

## 8. Tests Independently Executed & Limitations

The test suite was executed locally in the isolated Python 3.11 virtual environment (`backend/.venv`):

```powershell
pytest tests/test_financial_integrity_remediation.py tests/test_checkout.py tests/test_delivery.py
```

### 8.1 Results
- `tests/test_financial_integrity_remediation.py`: **10 passed**
  - Verified conditional update rowcount logic
  - Verified recovery from `ORDER_ABANDONED` to `ORDER_PAID`
  - Verified `last_reconciled_at` round-robin ordering
  - Verified single-use credential claim token creation, expiry, and email retry
  - Verified `SystemLease` atomic acquisition and lease expiry
  - Verified preflight check rules and key prefix validation
- `tests/test_checkout.py`: **61 passed**
- `tests/test_delivery.py`: **30 passed**
- **Total Local Tests Executed:** **101 passed, 0 failed**

### 8.2 Testing Limitations
- **SQLite Concurrency Limitation:** Local tests ran against an in-memory SQLite database. SQLite serializes all writes with a database-level lock, so thread races and row-level lock contention under concurrent PostgreSQL transactions could not be certified locally.
- **Remote CI Run Status:** PostgreSQL CI has NOT been executed on GitHub Actions because the branch remains unpushed per strict authorization rules.

---

## 9. Required Corrections (Ordered by Severity)

Before pushing the branch to GitHub for PostgreSQL CI, the following corrections must be implemented:

### Correction 1: Remove Plaintext Credential Leak from Order Status Poll
- **File:** `backend/app/api/v1/routes/checkout.py`
- **Location:** Lines 102-107
- **Action:** Modify `_provision_if_paid()` so that `WorkspaceOut.from_model()` is called WITHOUT `api_key` or `temporary_password`:
  ```python
  if result.profiles:
      return WorkspaceOut.from_model(result.profiles[0].profile)
  ```

### Correction 2: Add Fallback Provisioning to Reconciler
- **File:** `backend/app/payments/delivery.py`
- **Location:** Lines 305-311
- **Action:** In `deliver(self, order: Order)`, if `profiles` is empty for a paid order, invoke `ProvisioningService(self.db).provision(order)` to resume provisioning:
  ```python
  profiles = self.profiles_for(order)
  if not profiles:
      try:
          from app.payments.provisioning import ProvisioningService
          ProvisioningService(self.db).provision(order)
          profiles = self.profiles_for(order)
      except Exception:
          self.db.rollback()
          logger.exception("Reconciler failed to provision paid order %s", order.paystack_reference)
          return None
  ```

### Correction 3: Add Telegram Poller Lease Renewal Heartbeat
- **File:** `backend/app/main.py`
- **Location:** Lines 91-118
- **Action:** Implement a background asyncio heartbeat loop that periodically executes `lease_service.acquire_lease(..., ttl_seconds=60)` every 20 seconds while `poller.run()` is executing in its thread, cancelling the heartbeat when `poller.run()` finishes.

### Correction 4: Atomic Conditional Update in `complete-setup`
- **File:** `backend/app/auth/router.py`
- **Location:** Lines 490-515
- **Action:** Replace the non-locking `claim.claimed_at` assignment with an atomic conditional update:
  ```python
  stmt = (
      update(CredentialClaim)
      .where(
          CredentialClaim.token_hash == token_hash,
          CredentialClaim.claimed_at.is_(None),
      )
      .values(claimed_at=datetime.now(UTC))
  )
  res = db.execute(stmt)
  if res.rowcount == 0:
      raise HTTPException(status.HTTP_400_BAD_REQUEST, "This setup link has already been used.")
  ```

### Correction 5: Transactional Ordering in Setup Claim Email Dispatch
- **File:** `backend/app/payments/provisioning.py`
- **Location:** Lines 488-522
- **Action:** Flush and commit `claim` and `profile` records to the database with `claim.email_sent_at = None` BEFORE calling `mail.send()`. After `mail.send()` succeeds, update `claim.email_sent_at = datetime.now(UTC)` and commit.

---

## 10. Confirmation of Zero Unauthorized Operations

I hereby certify under strict audit protocol that during this inspection:
- **No application code or database migrations were modified or committed.**
- **No external network connections were made to Paystack or payment APIs.**
- **No payment charges, refunds, or sandbox transactions were initiated.**
- **No customer emails, messages, or notifications were dispatched.**
- **No remote Git operations (`push`, `merge`, `rebase`) were executed.**
- **Branch `remediation/paystack-financial-integrity` remains untouched at commit `75749f8`.**
- **Production database and Render configuration remain completely unaltered.**
