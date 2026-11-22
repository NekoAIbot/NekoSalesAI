# NERA — POSTGRESQL CI FOLLOW-UP: CONCURRENCY AND COVERAGE GAP ASSESSMENT

**Document Type:** Technical Gap Assessment & Concurrency Test Engineering Plan  
**Repository:** `C:\NekoProjects\NekoSalesAI`  
**Branch:** `remediation/paystack-financial-integrity`  
**Audited Commit:** `f4e9e9e66717234f44718d595f425b37df17915e`  
**Audit Date:** 2026-11-22  
**Audit Nature:** Strictly Read-Only  

---

## 1. Executive Summary & Verdict

The initial PostgreSQL CI workflow execution (`Run 44979187289`) verified that Alembic migrations run cleanly through revision `c3e7f1a8b9d2`, preflight checks pass, and all 118 included tests pass under Python 3.11 and PostgreSQL 16.

However, an in-depth source code inspection of the existing test suites confirms a critical limitation: **every test currently asserting "concurrency" or "competing workers" actually executes sequentially on a single thread sharing a single SQLAlchemy session.** Sequential invocation does not trigger simultaneous row locking, race conditions, or transactional isolation boundaries.

The underlying application design (atomic conditional updates, unique constraints, and transaction rollback boundaries) is structurally sound and ready for real concurrency testing.

### Assessment Verdict

### **`READY FOR CONCURRENCY TEST IMPLEMENTATION.`**

*(No destructive refactoring of the application architecture is required; the immediate requirement is implementing genuine multi-threaded, multi-transaction concurrency tests against PostgreSQL 16 in CI).*

---

## 2. Detailed Inspection: Sequential Simulations vs. Genuine Concurrency

The inspection evaluated all concurrency tests in [backend/tests/test_financial_integrity_remediation.py](file:///C:/NekoProjects/NekoSalesAI/backend/tests/test_financial_integrity_remediation.py).

### 2.1 `test_atomic_settlement_single_winner`
* **Source Location:** `backend/tests/test_financial_integrity_remediation.py:116-146`
* **Inspection Finding:**
  ```python
  # First settlement succeeds
  res1 = checkout.confirm(charge)
  assert res1.is_paid

  # Second settlement attempt receives the paid order without re-sending receipt
  res2 = checkout.confirm(charge)
  assert res2.is_paid
  assert receipt_counter[0] == 1, "Receipt must be dispatched exactly once"
  ```
* **Execution Reality:** **SEQUENTIAL.**
  - Uses a single `db: Session` instance.
  - Worker 1 completes the entire `confirm()` method, executes `db.commit()`, and returns.
  - Worker 2 executes only *after* Worker 1 has completely finished.
  - This verifies idempotency on repeated calls, but does **not** test simultaneous database transactions racing to execute `UPDATE orders SET status = ORDER_PAID ... WHERE id = :id AND status != ORDER_PAID`.

### 2.2 `test_email_dispatch_two_workers_competing_mutual_exclusion`
* **Source Location:** `backend/tests/test_financial_integrity_remediation.py:526-563`
* **Inspection Finding:**
  ```python
  # Worker 1 acquires dispatch lease
  with patch.object(mail_module, "send"):
      res1 = prov.dispatch_claim_email(claim, worker_id="worker_alpha", lease_seconds=60)
      assert res1 is True

  # Worker 2 attempts dispatch -> rejected because email_sent_at is set or leased
  with patch.object(mail_module, "send"):
      res2 = prov.dispatch_claim_email(claim, worker_id="worker_beta")
      assert res2 is False
  ```
* **Execution Reality:** **SEQUENTIAL.**
  - Worker 1 executes `dispatch_claim_email()`, sends mail, sets `email_sent_at`, and commits.
  - Worker 2 is invoked only after Worker 1 has completed.
  - This tests that an already-leased or already-sent claim cannot be re-dispatched, but does **not** test two simultaneous database transactions racing to acquire the atomic lease at the exact same millisecond.

### 2.3 `test_provisioning_two_workers_concurrent_no_duplicates`
* **Source Location:** `backend/tests/test_financial_integrity_remediation.py:732-757`
* **Inspection Finding:**
  ```python
  # First worker provisions
  res1 = prov.provision(test_order)
  assert len(res1.profiles) == 1

  # Second worker provisions concurrently
  res2 = prov.provision(test_order)
  assert len(res2.profiles) == 1
  ```
* **Execution Reality:** **SEQUENTIAL.**
  - Despite the name asserting "concurrent", `res1` completes and commits before `res2` begins.
  - It does **not** test two threads simultaneously executing `INSERT INTO workspace_profiles` or `INSERT INTO credential_claims`, nor does it verify that PostgreSQL unique constraint violations (`uq_credential_claims_order_id`) are safely handled and rolled back concurrently.

### 2.4 `test_complete_setup_atomic_conditional_update`
* **Source Location:** `backend/tests/test_financial_integrity_remediation.py:782-810`
* **Execution Reality:** **SEQUENTIAL.**
  - Request 1 calls `complete_setup()`, consumes the token, updates the password, rotates the key, and commits.
  - Request 2 is called in the next line. This tests serial replay rejection, not simultaneous redemption collision.

### 2.5 `test_lease_old_worker_renewal_and_release_rejected_after_new_owner`
* **Source Location:** `backend/tests/test_financial_integrity_remediation.py:655-675`
* **Execution Reality:** **SEQUENTIAL.**
  - State is manually manipulated in the test fixture between sequential calls to `ls1` and `ls2`.

---

## 3. Untested PostgreSQL Concurrency Scenarios & Test Architecture

To achieve true concurrency verification against PostgreSQL 16, tests must run across **independent OS threads, each with its own dedicated SQLAlchemy Session and physical database connection**, synchronized to execute database write queries simultaneously.

```
       Thread 1 (Worker Alpha)                      Thread 2 (Worker Beta)
   ┌───────────────────────────────┐            ┌───────────────────────────────┐
   │ Connection A (Dedicated Session)│          │ Connection B (Dedicated Session)│
   └──────────────┬────────────────┘            └──────────────┬────────────────┘
                  │                                            │
                  └───────────────► Barrier.wait() ◄───────────┘
                                  (Simultaneous Release)
                                           │
                  ┌────────────────────────┴───────────────────┐
                  ▼                                            ▼
       PostgreSQL Transaction 1                     PostgreSQL Transaction 2
   [UPDATE orders SET status=PAID...]           [UPDATE orders SET status=PAID...]
                  │                                            │
                  ▼                                            ▼
         Winner (1 Row Updated)                       Loser (0 Rows Updated)
```

### Proposed Concurrency Test Specifications

#### Test 1: Real Concurrent Settlement Collision (`test_pg_concurrent_settlement_single_winner`)
* **Mechanism:**
  - Initialize an order with status `ORDER_PENDING`.
  - Spawn two worker threads using `concurrent.futures.ThreadPoolExecutor(max_workers=2)`.
  - Each thread opens its own `SessionLocal()` (separate connection).
  - Use `threading.Barrier(2)` immediately before invoking `checkout.confirm(charge)`.
  - **Expected Outcome:**
    - Both threads complete without unhandled database deadlocks.
    - Exactly one thread records `res.is_paid == True` with the transition commit.
    - Exactly 1 customer receipt email is dispatched across both threads.
    - The final database state has `status = ORDER_PAID`, with zero duplicate side effects.

#### Test 2: Real Concurrent Provisioning Race (`test_pg_concurrent_provisioning_no_duplicates`)
* **Mechanism:**
  - Initialize an order marked `ORDER_PAID`.
  - Two threads with independent `SessionLocal()` instances race to call `ProvisioningService(session).provision(order)`.
  - Use `threading.Barrier(2)` before the insertion phase.
  - **Expected Outcome:**
    - One thread successfully inserts `WorkspaceProfile` and `CredentialClaim`.
    - The competing thread hits the PostgreSQL unique constraint (`uq_credential_claims_order_id` / `uq_workspace_profiles_org_role`), catches `IntegrityError`, executes `db.rollback()`, and retrieves the existing profile.
    - Verification: Database contains exactly 1 WorkspaceProfile, 1 User, and 1 CredentialClaim. Both threads return valid `ProvisioningResult` pointing to the identical profile ID.

#### Test 3: Real Concurrent Email Dispatch Lease Collision (`test_pg_concurrent_email_dispatch_mutual_exclusion`)
* **Mechanism:**
  - Create a pending `CredentialClaim` with `email_sent_at = None`.
  - Two threads with separate sessions synchronize on a barrier and invoke `prov.dispatch_claim_email(claim, worker_id=...)`.
  - Mock `mail.send` with an artificial 50ms delay to hold the transaction.
  - **Expected Outcome:**
    - Exactly one worker acquires the atomic lease (`return True`) and dispatches the email.
    - The competing worker receives `False` (0 rows updated by atomic CAS).
    - `mail.send` is invoked exactly once.

#### Test 4: Real Concurrent Setup Claim Redemption Race (`test_pg_concurrent_complete_setup_single_winner`)
* **Mechanism:**
  - Create an unredeemed `CredentialClaim`.
  - Two threads simultaneously submit `CompleteSetupRequest` to `complete_setup()` using separate database sessions.
  - **Expected Outcome:**
    - Exactly one request succeeds with HTTP 200 and receives the API key.
    - The racing request receives HTTP 400 (`"This setup link has already been used"`).
    - The user's password is set once, and the API key is rotated once.

#### Test 5: Real Concurrent Poller Lease Takeover (`test_pg_concurrent_lease_acquisition_mutual_exclusion`)
* **Mechanism:**
  - Two workers race to acquire the same lease name simultaneously from separate connections.
  - **Expected Outcome:**
    - Exactly one worker acquires the lease (`True`) and increments `fencing_token`.
    - The losing worker receives `False` without throwing uncaught database exceptions.

---

## 4. Test Suite Coverage Analysis

### Current CI Configuration
In [.github/workflows/financial-integrity-ci.yml](file:///C:/NekoProjects/NekoSalesAI/.github/workflows/financial-integrity-ci.yml#L71-L74), the test command is:
```yaml
pytest tests/test_financial_integrity_remediation.py tests/test_checkout.py tests/test_delivery.py -v --tb=short
```
This runs 118 tests:
- `test_financial_integrity_remediation.py`: 26 tests
- `test_checkout.py`: 61 tests
- `test_delivery.py`: 31 tests

### Omitted Test Suites
The local 145-test suite included two additional test files:

1. **`backend/tests/test_payment_environment.py` (15 tests):**
   - **Coverage:** Verifies key prefix validation (`sk_live_`, `sk_test_`), production environment guards, environment mismatch rejections, and fail-closed credential behavior.
   - **PostgreSQL Compatibility:** **100% compatible.** Pure unit tests requiring no database tables; executes in < 0.5s.
   - **Recommendation:** **INCLUDE in CI.** Vital security guard against credential misconfiguration.

2. **`backend/tests/test_poller_loop.py` (12 tests):**
   - **Coverage:** Verifies Telegram long-poll exponential backoff, failure quiet thresholds, payment reconciliation cycles on empty update batches, and delivery message routing.
   - **PostgreSQL Compatibility:** **100% compatible.** Uses mock session factories (`_NullSession`) and mock clients; executes in ~1.0s.
   - **Recommendation:** **INCLUDE in CI.** Ensures poller reconciliation and backoff logic are verified in every CI run.

### Recommended CI Configuration
Expanding the CI command to:
```yaml
pytest tests/test_financial_integrity_remediation.py tests/test_checkout.py tests/test_delivery.py tests/test_payment_environment.py tests/test_poller_loop.py -v --tb=short
```
Increases coverage from 118 to **145 tests** (+ new concurrent tests) with virtually zero CI runtime overhead (+1.5 seconds).

---

## 5. Telegram Poller Lease Fencing & Race Window Analysis

### 5.1 Architecture & Lifecyle Inspection
In [backend/app/main.py](file:///C:/NekoProjects/NekoSalesAI/backend/app/main.py#L118-L162), the poller lifecycle operates as:
1. `LeaseService.acquire_lease()` acquires `f"{label}_poller"` for 60 seconds with monotonic `fencing_token`.
2. A background `_heartbeat_loop()` attempts `renew_lease()` every 20 seconds.
3. The poller runs in a dedicated threadpool worker (`asyncio.to_thread(poller.run)`).

### 5.2 Identified Race Window: Stale Worker Window
Consider the following timeline:
* **$t = 0$s:** Worker A acquires lease (TTL = 60s, `fencing_token = 1`).
* **$t = 20$s:** Worker A renews lease (TTL extended to $t = 80$s).
* **$t = 30$s:** Worker A suffers a full network partition or process pause (e.g. system freeze, database unreachable).
* **$t = 80$s:** Lease expires in PostgreSQL.
* **$t = 81$s:** Worker B acquires lease (`fencing_token = 2`).
* **$t = 82$s:** Worker A unfreezes.

**What happens to Worker A?**
1. **Heartbeat Detection:** Worker A's heartbeat loop resumes and calls `renew_lease()`. PostgreSQL rejects the renewal (`acquired_by != worker_id` or `fencing_token != 1`). Worker A sets `fenced_out = True` and calls `poller.stop()`.
2. **The Race Window:** Between $t=82$s and the moment the heartbeat discovers the rejection (which can take up to the next heartbeat cycle or DB timeout), Worker A's poller loop could still be executing.
3. **In-Flight Telegram HTTP Calls:**
   - If Worker A was blocked in `TelegramClient.get_updates(timeout=25)`, that network socket to `api.telegram.org` remains open until Telegram returns or timeouts.
   - When Worker B simultaneously calls `getUpdates`, Telegram Bot API resolves this at the edge by terminating one request with **HTTP 409 Conflict** (`"terminated by other getUpdates request"`).
   - Once Worker A's call returns, `TelegramPoller.run()` and `drain()` check `if self._stopping: break`, stopping immediately.
4. **Outbound Messaging Leak:**
   - In `TelegramPoller._handle()`, messages are sent via `TelegramClient.send_message()`. The client does **not** check lease validity before dispatching messages.
   - In `TelegramPoller.reconcile_payments()`, reconciliation is called directly on `DeliveryService(db)`. The poller loop does not verify the `"payment_reconciler"` lease before reconciling.

### 5.3 Recommendation
1. Add an explicit check of `if self._stopping:` prior to invoking `reconcile_payments()` in `poller.run()`.
2. Implement automated tests verifying that when `fenced_out = True` is triggered, the poller exits within 1 cycle and never processes further batches.

---

## 6. GitHub Actions Node.js 20 Deprecation Warning

### Root Cause
The CI run emitted:
```
##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5.
```
- GitHub Actions hosted runners (`ubuntu-22.04`) have migrated default execution to Node.js 24.
- `actions/checkout@v4` and `actions/setup-python@v5` originally declared Node.js 20 runtimes.
- GitHub's runner automatically executes them under Node.js 24 with a non-blocking deprecation warning.

### Recommended Resolution
To eliminate the warning without breaking the workflow:
1. Update `actions/checkout@v4` to `actions/checkout@v4.2.2` (or the latest patch release).
2. Update `actions/setup-python@v5` to `actions/setup-python@v5.4.0`.
3. If the warning persists pending GitHub upstream releases, suppress runner warnings by setting `FORCE_JAVASCRIPT_ACTIONS_TO_NODE20: true` in the workflow environment, or leave as-is since the warning does not affect test execution or exit codes.

---

## 7. Prioritized Implementation & Verification Plan

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        PRIORITIZED IMPLEMENTATION PLAN                                 │
├──────┬──────────────────────────────────────────┬──────────────────────────┬───────────┤
│ Step │ Action Description                       │ Target Files             │ Priority  │
├──────┼──────────────────────────────────────────┼──────────────────────────┼───────────┤
│ 1    │ Implement Multi-Threaded PostgreSQL      │ tests/test_financial_    │ **P0**    │
│      │ Concurrency Test Suite (5 Scenarios)     │ integrity_remediation.py │           │
├──────┼──────────────────────────────────────────┼──────────────────────────┼───────────┤
│ 2    │ Expand CI Workflow Test Scope            │ .github/workflows/       │ **P1**    │
│      │ (Add test_payment_environment & poller)  │ financial-integrity-ci   │           │
├──────┼──────────────────────────────────────────┼──────────────────────────┼───────────┤
│ 3    │ Guard Poller Reconciliation with Lease   │ app/messaging/poller.py  │ **P2**    │
│      │ State Check                              │ app/main.py              │           │
├──────┼──────────────────────────────────────────┼──────────────────────────┼───────────┤
│ 4    │ Update CI Action Versions                │ .github/workflows/       │ **P3**    │
│      │ (Clean Node 20 deprecation warning)      │ financial-integrity-ci   │           │
└──────┴──────────────────────────────────────────┴──────────────────────────┴───────────┘
```

---

## 8. Exact Acceptance Criteria for the Next CI Run

Before merging `remediation/paystack-financial-integrity` into `main`, the next CI run must satisfy:

1. **True PostgreSQL Concurrency Tests Passing:**
   - [ ] Concurrent settlement test proves exactly 1 winner under simultaneous threads.
   - [ ] Concurrent provisioning test proves zero duplicate profiles/claims under simultaneous threads.
   - [ ] Concurrent email dispatch test proves atomic lease mutual exclusion under simultaneous threads.
   - [ ] Concurrent setup redemption test proves single-use CAS under simultaneous threads.
   - [ ] Concurrent lease takeover test proves fencing token monotonicity under simultaneous threads.
2. **Comprehensive Test Coverage:**
   - [ ] All 145+ tests executed and passing against PostgreSQL 16 in CI.
   - [ ] `tests/test_payment_environment.py` (15 tests) passing in CI.
   - [ ] `tests/test_poller_loop.py` (12 tests) passing in CI.
3. **Clean CI Diagnostics:**
   - [ ] Zero test failures, zero test errors.
   - [ ] Alembic migrations upgrade cleanly to head.
   - [ ] Preflight check reports all checks passing on PostgreSQL.

---

## Final Assessment Verdict

### **`READY FOR CONCURRENCY TEST IMPLEMENTATION.`**
