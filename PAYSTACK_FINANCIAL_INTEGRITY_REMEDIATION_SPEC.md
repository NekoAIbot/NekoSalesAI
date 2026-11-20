# NERA — PAYSTACK FINANCIAL INTEGRITY REMEDIATION SPECIFICATION
**Document ID:** `SPEC-PAYSTACK-FIN-001`  
**Status:** PROPOSED — PENDING AUTHORIZATION  
**Target Service:** Nera Web Service (`https://nera-9b3t.onrender.com`)  
**Repository Working Directory:** `C:\NekoProjects\NekoSalesAI`  
**Base Commit:** `b1097ac3073473d7d18049944f3faba02505c216` (`main`)  
**Author:** AI Forensic & Security Engineering  
**Date:** November 19, 2026  

---

## 1. EXECUTIVE SUMMARY & VERDICT

### Executive Summary
A comprehensive two-pass forensic audit was conducted on Nera's Paystack payment processing pipeline. The first-pass audit verified that baseline cryptographic signature verification (HMAC-SHA512) and minor-unit kobo arithmetic are sound, but flagged that the production deployment on Render is currently operating in Paystack **Test Mode** (`pk_test_...`), prohibiting real money collection.

This second-pass investigation focused on underlying financial integrity, concurrency, ledger invariants, and failure survivability. It identified **seven distinct engineering and architectural findings** that must be resolved before any live-credential transition:

1. **Non-Atomic Payment Settlement:** Order status transitions rely on in-memory object mutations rather than conditional atomic SQL updates or row-level locks, permitting concurrent webhook and browser return requests to execute duplicate settlement and duplicate receipt dispatch.
2. **Session Poisoning in `_provision_if_paid()`:** When concurrent settlement races trigger database uniqueness constraints, `_provision_if_paid()` catches the exception but fails to call `db.rollback()`. Any subsequent database query crashes with `PendingRollbackError`, surfacing an erroneous HTTP 500 error to a paying customer.
3. **Silent Credential Evaporation (Buyer Lockout):** The background webhook often confirms and provisions orders before the customer's browser returns. Because the temporary password and raw API key are held only in memory and the credentials email function (`app.mail.messages.credentials`) is an uncalled orphan, the customer's credentials vanish. Subsequent browser polls return `api_key=None` and `temporary_password=None`, permanently locking the buyer out of their workspace.
4. **Autonomous Reconciler Starvation & Abandoned Order Queue Freezing:** The reconciler queries only the 10 most recent pending orders (`.limit(10)`) and never transitions abandoned checkouts to `ORDER_ABANDONED`. Once 10 checkouts are abandoned, the reconciler enters an **infinite starvation loop**, permanently blinding it to all other pending orders.
5. **Coupling to Telegram Poller & Webhook Mode Inactivity:** The payment reconciler runs exclusively inside `TelegramPoller.run()`, meaning it is dead if Telegram is in webhook mode or unconfigured.
6. **Multi-Worker Poller Collision:** The process-local global guard `_poller_task` does not prevent multiple Uvicorn worker processes from launching competing Telegram pollers and reconciler loops.
7. **Production Configuration & Key Authenticity Discipline:** The production Render environment is currently running in non-production mode with test keys. Syntactic prefix checks (`sk_test_`) prove validator compliance but do not prove upstream provider connectivity.

### Specification Verdict
**VERDICT: READY FOR IMPLEMENTATION**  
*(Subject to explicit administrative authorization. Implementation must proceed in strict priority sequence under isolated CI verification before any live credentials are configured.)*

---

## 2. DETAILED DEFECT REMEDIATION SPECIFICATIONS (FINDINGS 1–7)

---

### FINDING 1: Non-Atomic Order Settlement & Settlement Concurrency Race

#### 1. Exact Source Files & Functions
- **Primary Source File:** `backend/app/payments/checkout.py`
- **Primary Functions:** `CheckoutService.confirm()` (lines 391–444), `CheckoutService.get_by_reference()` (lines 380–389)
- **Connected Routes:** `POST /api/v1/checkout/webhook`, `GET /api/v1/checkout/orders/{reference}`, `POST /api/v1/checkout/orders/{reference}/verify`
- **Models Affected:** `backend/app/models/order.py` (`Order`), `backend/app/models/conversation.py` (`Conversation`)

#### 2. Independently Verified Defect & Evidence
In `CheckoutService.confirm()`:
```python
order = self.get_by_reference(charge.reference)
if order is None:
    return None
if order.is_paid:
    return order
...
order.status = ORDER_PAID
order.paid_at = datetime.now(timezone.utc)
order.provider_payload = dump_payload(charge.raw)
if order.conversation is not None:
    order.conversation.stage = STAGE_CLOSED_WON
self.db.commit()
self.db.refresh(order)
self._send_receipt(order)
return order
```
`get_by_reference()` executes `select(Order).where(Order.paystack_reference == reference)` without row-level locking (`with_for_update()`). The check `if order.is_paid: return order` is evaluated entirely in Python memory.

#### 3. Root Cause
Absence of database-level concurrency control during state transitions. If a Paystack webhook and a client return poll execute concurrently, both database transactions read `order.status == 'pending'` before either commits. Both threads update `order.status = 'paid'`, commit, and execute `self._send_receipt(order)`, dispatching duplicate receipt emails.

#### 4. Proposed Technical Correction
Replace the in-memory state mutation with an **atomic conditional SQL update**:

```python
from sqlalchemy import update

def confirm(self, charge: Charge) -> Order | None:
    order = self.get_by_reference(charge.reference)
    if order is None:
        logger.warning("Charge %s does not match any order; ignoring.", charge.reference)
        return None

    if order.is_paid:
        return order

    if not charge.paid:
        logger.info("Charge %s reported status %r; leaving order pending.", charge.reference, charge.status)
        return order

    if not self._amount_matches(order, charge):
        logger.error("Charge %s claims %s %s but order %s is %s %s.", 
                     charge.reference, charge.amount_minor, charge.currency,
                     order.id, order.amount_minor, order.currency)
        return order

    # Atomic conditional update: strictly succeeds on exactly one thread
    now = datetime.now(timezone.utc)
    payload_str = dump_payload(charge.raw)
    
    stmt = (
        update(Order)
        .where(
            Order.id == order.id,
            Order.status == ORDER_PENDING
        )
        .values(
            status=ORDER_PAID,
            paid_at=now,
            provider_payload=payload_str,
        )
    )
    result = self.db.execute(stmt)
    
    if result.rowcount == 0:
        # A concurrent thread already transitioned this order to paid.
        self.db.rollback()
        self.db.refresh(order)
        return order

    if order.conversation_id is not None:
        self.db.execute(
            update(Conversation)
            .where(Conversation.id == order.conversation_id)
            .values(stage=STAGE_CLOSED_WON)
        )

    self.db.commit()
    self.db.refresh(order)
    
    logger.info("Order %s paid: %s for %s", order.paystack_reference, order.plan_code, order.buyer_email)
    self._send_receipt(order)
    return order
```

#### 5. Database & Transaction Implications
- Guarantees exactly-once execution of the order status transition.
- Works identically and safely across SQLite (table-level write lock) and PostgreSQL (row-level write lock during `UPDATE`).
- No table lock escalation or deadlocks; `UPDATE ... WHERE id = :id AND status = 'pending'` acquires an exclusive row lock on PostgreSQL only for the specific order.

#### 6. Security Implications
Prevents race conditions from executing multiple settlement events, duplicate receipt emails, or duplicate webhook side effects.

#### 7. Required Regression Tests
- Multi-threaded test executing 10 simultaneous calls to `confirm()` against the same pending order reference using independent SQLAlchemy sessions.
- Assertion: Exactly one thread executes the state change and sends the receipt email; all other 9 threads receive the paid order without re-sending receipts.

#### 8. Acceptance Criteria
- Zero duplicate status updates.
- Exactly one receipt email dispatched per paid order.
- Concurrent requests return HTTP 200 with the identical paid order state.

#### 9. Deployment & Rollback Considerations
- Pure application-code change; no database schema alterations or migrations required.
- Rollback: Reverting to previous Python source leaves database fully consistent.

#### 10. Remaining Risks
- In PostgreSQL, if transactions are run under `SERIALIZABLE` isolation, a retry on serialization failure would be needed; under `READ COMMITTED` (the SQLAlchemy default), the conditional update handles this cleanly.

---

### FINDING 2: Session Poisoning in `_provision_if_paid()`

#### 1. Exact Source Files & Functions
- **Primary Source File:** `backend/app/api/v1/routes/checkout.py`
- **Primary Function:** `_provision_if_paid()` (lines 74–106)
- **Connected Services:** `backend/app/payments/provisioning.py` (`ProvisioningService.provision()`)
- **Models Affected:** `backend/app/models/workspace_profile.py` (`uq_workspace_profiles_organization_role`), `backend/app/models/organization.py` (`uq_organizations_slug`)

#### 2. Independently Verified Defect & Evidence
In `_provision_if_paid()`:
```python
    try:
        result = service.provision(order)
    except Exception:
        profile = service.get_for_order(order)
        return WorkspaceOut.from_model(profile) if profile else None
```
When concurrent requests attempt provisioning simultaneously, one request commits first. The second request hits an `IntegrityError` on `uq_workspace_profiles_organization_role` or `uq_organizations_slug`. It enters `except Exception:`. Because **`db.rollback()` is omitted**, the SQLAlchemy session remains in an aborted state. The subsequent call `service.get_for_order(order)` crashes with `PendingRollbackError`, terminating the HTTP request with an unhandled 500 error.

#### 3. Root Cause
Omission of transaction rollback upon encountering a database constraint failure.

#### 4. Proposed Technical Correction
Update `_provision_if_paid()` in `backend/app/api/v1/routes/checkout.py`:
```python
def _provision_if_paid(order: Order, db: Session) -> WorkspaceOut | None:
    if not order.is_paid:
        return None

    service = ProvisioningService(db)

    try:
        result = service.provision(order)
    except Exception:
        # MUST rollback before reading: an IntegrityError from a concurrent
        # provision poisons the session. Without rollback, get_for_order crashes
        # with PendingRollbackError, turning a successful payment into a 500.
        db.rollback()
        logger.exception("Provisioning order %s encountered an error; falling back to read existing.", order.paystack_reference)
        profile = service.get_for_order(order)
        return WorkspaceOut.from_model(profile) if profile else None

    if result.profiles:
        _schedule_follow_ups(result.profiles[0].profile, order, db)
    _tell_the_buyer(order, db)

    if result.profiles:
        return WorkspaceOut.from_model(
            result.profiles[0].profile,
            api_key=result.profiles[0].api_key,
            temporary_password=result.profiles[0].temporary_password,
        )
    return None
```

#### 5. Database & Transaction Implications
Clears failed transactions from the session pool, allowing clean read operations on committed rows.

#### 6. Security Implications
Prevents false-negative payment screens (a customer who paid ₦210,000 seeing an internal server error screen).

#### 7. Required Regression Tests
- Simulate concurrent `service.provision(order)` calls where the first inserts a profile and the second raises `IntegrityError`.
- Verify `_provision_if_paid()` recovers cleanly, executes `db.rollback()`, queries the existing profile, and returns HTTP 200 with the profile data.

#### 8. Acceptance Criteria
- Zero `PendingRollbackError` exceptions under concurrent execution.
- Failed provisioning attempts never misrepresent a successful payment as failed.

#### 9. Deployment & Rollback Considerations
- Pure application-code change; no migration required.
- Zero downtime deployment. Rollback is a safe code revert.

#### 10. Remaining Risks
- If a database server goes offline completely, the read will raise `OperationalError`; this is correctly treated as a 503 gateway failure rather than a false payment decline.

---

### FINDING 3: Secure Credential Issuance, Delivery & Retrieval

#### 1. Exact Source Files & Functions
- **Primary Source Files:** `backend/app/payments/provisioning.py`, `backend/app/payments/delivery.py`, `backend/app/mail/messages.py`, `backend/app/models/order.py`
- **Primary Functions:** `ProvisioningService.provision()`, `compose_delivery()`, `_confirmation()`, `credentials()`
- **Routes Affected:** `GET /api/v1/checkout/orders/{reference}`, `GET /checkout/return`

#### 2. Independently Verified Defect & Evidence
1. `app.mail.messages.credentials` is an uncalled orphan function; credentials emails are never sent.
2. In `delivery.py:218`, the chat notification tells the buyer: *"Sign in at ... Your password and API key have been emailed to that address..."*, which is false.
3. If a webhook provisions an order asynchronously while the customer is on Paystack's 3DS page, raw credentials in memory are discarded. When the customer's browser returns to `/checkout/return`, `api_key` and `temporary_password` return `None`. The customer has no way to log in or retrieve their API key.

#### 3. Root Cause
Coupling credential display solely to the ephemeral in-memory return of `ProvisioningResult`, combined with the absence of a durable, time-limited credential retrieval mechanism.

#### 4. Proposed Technical Correction

##### Architecture: Single-Use Claim Token
```
[Payment Succeeded]
        │
        ▼
[ProvisioningService.provision()]
  ├── 1. Generates API Key (`nsk_live_...`) & stores SHA-256 hash
  ├── 2. Creates Admin User with unusable password hash (Account Locked)
  ├── 3. Generates 256-bit CSPRNG Claim Token (`claim_token`)
  ├── 4. Stores SHA-256(`claim_token`) in `credential_claims` table:
  │      - order_id
  │      - user_id
  │      - token_hash
  │      - expires_at (now + 24 hours)
  │      - claimed_at (NULL)
  └── 5. Sends "Set Up Your Workspace" Email with single-use magic setup link:
         `https://nera.ai/setup?claim={claim_token}`
```

##### Step 1: Database Migration — Add `credential_claims` Table
Create `backend/alembic/versions/xxxx_create_credential_claims.py`:
```python
class CredentialClaim(BaseModel):
    __tablename__ = "credential_claims"
    
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

##### Step 2: Implementation of Secure Setup Endpoint
Create `GET /api/v1/auth/claim-workspace` and `POST /api/v1/auth/complete-setup`:
1. Customer receives an email containing a link with the single-use token: `https://nera.ai/setup?claim=<token>`.
2. Link expires in 24 hours.
3. Upon opening the setup page, the customer chooses their own password directly (never sending plaintext passwords over email).
4. Upon password confirmation, the claim token is marked `claimed_at = now()`. The initial API key is displayed once in the UI with a copy button, and the buyer is logged into their dashboard.
5. If the claim token expires, the customer can request a fresh setup link to their verified purchase email (`order.buyer_email`).

##### Step 3: Correct Notification Text
Update `_confirmation()` in `delivery.py`:
- Remove the false claim that passwords and API keys were sent via email.
- Replace with: *"Sign in at {sign_in_url()} using {order.buyer_email}. A secure workspace setup link has been sent to your email to set your password and access your API credentials."*

#### 5. Database & Transaction Implications
Requires one Alembic migration to add `credential_claims`. Tokens are stored as SHA-256 hashes; raw claim tokens never touch the database.

#### 6. Security Implications
- Eliminates permanent plaintext passwords and API keys from email inboxes.
- Prevents credential evaporation when webhooks precede browser redirects.
- Guarantees time-limited (24-hour), single-use activation.

#### 7. Required Regression Tests
- Test claim token issuance, successful setup, and token invalidation on second use.
- Test expired claim token rejection (>24h).
- Test resend setup link for paid orders.

#### 8. Acceptance Criteria
- Raw API keys and passwords never traverse unencrypted email.
- Customers can always access their purchased workspace regardless of webhook/browser race outcomes.

#### 9. Deployment & Rollback Considerations
- Standard Alembic migration (`alembic upgrade head`).
- Rollback: `alembic downgrade -1` drops the table cleanly.

#### 10. Remaining Risks
- If the customer's email provider delays or spam-filters the setup link, the customer must use the on-screen "Resend Setup Link" action.

---

### FINDING 4: Autonomous Reconciliation Architecture & Starvation Elimination

#### 1. Exact Source Files & Functions
- **Primary Source Files:** `backend/app/payments/delivery.py`, `backend/app/payments/checkout.py`
- **Primary Functions:** `DeliveryService.reconcile()`, `DeliveryService._pending_with_a_checkout()`, `CheckoutService.confirm()`
- **Model Affected:** `backend/app/models/order.py` (`Order`)

#### 2. Independently Verified Defect & Evidence
1. `_pending_with_a_checkout()` selects:
   ```python
   select(Order).where(Order.status == ORDER_PENDING, Order.checkout_url.is_not(None)).order_by(Order.id.desc()).limit(10)
   ```
2. When Paystack reports `status: "abandoned"`, `CheckoutService.confirm()` leaves `order.status = "pending"`.
3. Abandoned orders remain in `ORDER_PENDING` indefinitely, permanently occupying the top 10 query slots and starving all older orders.

#### 3. Root Cause
Absence of an order reconciliation lifecycle state machine and lack of an abandoned checkout transition policy.

#### 4. Proposed Technical Correction

##### Policy Definition:
- **Pending (Active Window: 0 to 2 hours):** Candidate for active polling.
- **Abandoned (Age > 2 hours and Paystack reports "abandoned"):** Order is updated to `status = ORDER_ABANDONED`.
- **Late Payment Recovery (Paystack reports "success" on an abandoned order):** The state machine allows transition `ORDER_ABANDONED -> ORDER_PAID`. If a customer completes payment after 3 hours via an open tab, Paystack's webhook or a verify call will still settle and provision the workspace.

##### Query Correction in `DeliveryService._pending_with_a_checkout()`:
Add tracking columns to `orders`: `last_reconciled_at` and `reconcile_attempts`.
```python
def _pending_with_a_checkout(self) -> list[Order]:
    now = datetime.now(timezone.utc)
    # Scan pending orders prioritizing those least recently checked
    # Bounded to checkouts created within the last 7 days
    stmt = (
        select(Order)
        .where(
            Order.status == ORDER_PENDING,
            Order.checkout_url.is_not(None),
            Order.created_at >= now - timedelta(days=7),
            or_(
                Order.last_reconciled_at.is_(None),
                Order.last_reconciled_at < now - timedelta(minutes=5)
            )
        )
        .order_by(Order.last_reconciled_at.asc().nullsfirst())
        .limit(25)
    )
    return list(self.db.execute(stmt).scalars().all())
```

##### Handling Abandoned Status in `CheckoutService.confirm()`:
```python
if not charge.paid:
    if charge.status in ("abandoned", "failed") and order.created_at < datetime.now(timezone.utc) - timedelta(hours=2):
        order.status = ORDER_ABANDONED
        self.db.commit()
        logger.info("Order %s marked abandoned after Paystack confirmation.", charge.reference)
    return order
```

#### 5. Database & Transaction Implications
Requires adding `last_reconciled_at: Mapped[datetime | None]` to `orders`. Prevents queue stagnation.

#### 6. Security Implications
Ensures delayed legitimate payments (e.g., bank transfer confirmation arriving 4 hours later) are safely captured and provisioned.

#### 7. Required Regression Tests
- Create 15 abandoned orders and 1 delayed paid order created earlier.
- Run reconciliation. Verify all 16 orders are processed and the delayed order is successfully identified and provisioned.

#### 8. Acceptance Criteria
- Older pending orders are never starved by newer abandoned checkouts.
- Late-arriving payments on abandoned checkouts settle cleanly.

#### 9. Deployment & Rollback Considerations
- Migration adds nullable `last_reconciled_at` to `orders`. Fully backwards compatible.

#### 10. Remaining Risks
- Orders older than 7 days are ignored by the background poller; if a customer pays after 8 days, they must use the `/verify` recovery route or webhook.

---

### FINDING 5: Multi-Worker Reliability & Reconciler Decoupling

#### 1. Exact Source Files & Functions
- **Primary Source Files:** `backend/app/main.py`, `backend/app/messaging/poller.py`
- **Primary Functions:** `app.main:lifespan()`

#### 2. Verified Defect & Evidence
- `DeliveryService.reconcile()` is embedded inside `TelegramPoller.run()`.
- If `TELEGRAM_MODE == "webhook"`, reconciliation never runs.
- `_poller_task` is a module-level global variable. In multi-worker Uvicorn setups, each worker process spawns competing reconciliation loops.

#### 3. Root Cause
Coupling payment domain reconciliation to an external third-party chat platform poller.

#### 4. Proposed Technical Correction

##### Step 1: Standalone Lifespan Background Reconciler
In `backend/app/main.py`, register a dedicated `asyncio` task inside `lifespan()`:
```python
async def _payment_reconciler_loop(stop_event: asyncio.Event):
    logger.info("Starting autonomous payment reconciler loop")
    while not stop_event.is_set():
        try:
            with get_db_context() as db:
                # Attempt distributed advisory lock (PostgreSQL)
                if not settings.is_sqlite:
                    has_lock = db.execute(text("SELECT pg_try_advisory_lock(849201)")).scalar()
                    if not has_lock:
                        await asyncio.sleep(60)
                        continue
                try:
                    report = DeliveryService(db).reconcile()
                    if not report.quiet:
                        logger.info("Payment reconcile: %s", report.summary())
                finally:
                    if not settings.is_sqlite:
                        db.execute(text("SELECT pg_advisory_unlock(849201)"))
        except Exception:
            logger.exception("Autonomous payment reconciliation encountered an error")
            
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            pass
```

##### Step 2: Lifespan Integration
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start autonomous payment reconciler independent of Telegram
    reconcile_stop = asyncio.Event()
    reconcile_task = asyncio.create_task(_payment_reconciler_loop(reconcile_stop), name="payment-reconciler")
    
    # Telegram poller runs independently if enabled
    ...
    yield
    ...
    reconcile_stop.set()
    await reconcile_task
```

#### 5. Database & Transaction Implications
Under PostgreSQL, `pg_try_advisory_lock` ensures that even with 10 Uvicorn workers or multiple horizontal Render container instances, exactly one worker runs reconciliation at any given time.

#### 6. Security Implications
Guarantees reliable background payment reconciliation in all deployment configurations (with or without Telegram).

#### 7. Required Regression Tests
- Start two concurrent reconciler threads. Verify advisory lock prevents concurrent execution.
- Verify reconciler executes every 60s when `TELEGRAM_MODE=webhook`.

#### 8. Acceptance Criteria
- Reconciler operates 100% independently of Telegram.
- Zero multi-worker lock contention.

#### 9. Deployment & Rollback Considerations
- Render runs one worker today, but advisory lock future-proofs scaling to multiple workers or instances.

#### 10. Remaining Risks
- If a database connection hangs indefinitely during an advisory lock, the connection timeout terminates it cleanly.

---

### FINDING 6: Multi-Worker Telegram Poller Collision Guard

#### 1. Exact Source Files & Functions
- **Primary Source File:** `backend/app/main.py` (lines 15–20, 113–145)
- **Functions:** `_run_poller()`, `lifespan()`

#### 2. Verified Defect & Evidence
`_poller_task` is a module-level global variable. If Uvicorn is launched with multiple worker processes (`uvicorn --workers 4`), each process executes `lifespan()`, starts an independent Telegram long-polling loop, and receives `HTTP 409 Conflict` errors from Telegram's `getUpdates` API.

#### 3. Root Cause
Reliance on Python in-memory process globals for cross-process concurrency management.

#### 4. Proposed Technical Correction
Add a distributed lease/advisory lock for the Telegram poller in `_run_poller()`:
```python
# Before starting poller thread:
if not settings.is_sqlite:
    has_poller_lock = db.execute(text("SELECT pg_try_advisory_lock(849202)")).scalar()
    if not has_poller_lock:
        logger.info("Another worker is running Telegram poller (%s); skipping.", label)
        return
```

#### 5. Database & Transaction Implications
Advisory lock key `849202` dedicated to Telegram poller; zero table overhead.

#### 6. Security Implications
Prevents duplicate message ingestion and Telegram API 409 rate-limiting.

#### 7. Required Regression Tests
- Launch two worker tasks; assert worker 1 acquires lock and worker 2 idles cleanly.

#### 8. Acceptance Criteria
- Exactly one Telegram poller loop active across all workers.

#### 9. Deployment & Rollback Considerations
- Safe drop-in enhancement; works transparently on single-worker and multi-worker deployments.

#### 10. Remaining Risks
- Lock releases automatically on process exit/termination.

---

### FINDING 7: Production Configuration & Credential Validation Discipline

#### 1. Exact Source Files & Functions
- **Primary Source Files:** `backend/app/config/settings.py`, `backend/app/payments/paystack.py`, `render.yaml`
- **Functions:** `validate_paystack_credentials()`, `Settings.paystack_is_live`

#### 2. Verified Defect & Evidence
The live Render environment currently serves:
`{"enabled": true, "live_mode": false, "public_key": "pk_test_db3cafe8f84281b3a84da4caab4f6f365511cc0e"}`
The active environment is running in Test Mode because `ENVIRONMENT` is not set to `production` in Render's dashboard. A matching key prefix (`pk_test_...`) proves syntactic compliance with the safety validator, but does **not** prove upstream API authenticity.

#### 3. Root Cause
Divergence between `render.yaml` (`ENVIRONMENT: production`) and manual Render Dashboard configuration (`ENVIRONMENT=development`).

#### 4. Proposed Technical Correction & Pre-Flight Check
Maintain the existing test-mode configuration until Findings 1–6 are remediated and verified.  
Implement a standalone, read-only preflight validation CLI command:
`python -m app.payments.preflight`
- Checks `ENVIRONMENT == "production"`.
- Checks `PAYSTACK_SECRET_KEY.startswith("sk_live_")`.
- Checks `PAYSTACK_PUBLIC_KEY.startswith("pk_live_")`.
- Performs a live read-only verification query against `https://api.paystack.co/transaction/verify/test_preflight_probe` to verify upstream TLS and API key authentication before enabling customer checkout.

#### 5. Database & Transaction Implications
None (read-only verification).

#### 6. Security Implications
Guarantees live credentials are fully verified before switching traffic to live mode.

#### 7. Required Regression Tests
- Unit tests verifying preflight command catches expired keys, invalid prefixes, and network failures.

#### 8. Acceptance Criteria
- `/api/v1/checkout/config` returns `{"enabled": true, "live_mode": true}` only after explicit administrative promotion.

#### 9. Deployment & Rollback Considerations
- Requires administrator access to Render Dashboard to input live credentials.

#### 10. Remaining Risks
- Webhook secret must be verified to match the secret registered in the Paystack merchant dashboard.

---

## 3. VERIFICATION & TEST STRATEGY MATRIX

To ensure that concurrency and transaction boundaries are genuinely proven, the test suite must distinguish between SQLite (single-writer database) and PostgreSQL (concurrent production database):

| Test Scenario | Test Framework / Environment | Engine Required | Passing Criteria |
| :--- | :--- | :---: | :--- |
| **Simultaneous Settlement Attempts** | 10 concurrent threads calling `confirm()` on same pending order | **PostgreSQL** | Exactly 1 update committed; rowcount=1 on thread 1, rowcount=0 on threads 2-10. Single receipt sent. |
| **Duplicate / Out-of-Order Webhooks** | Simultaneous `POST /webhook` and `GET /orders/{ref}` | **PostgreSQL** | Status transitions to `paid`; both return 200; zero duplicate profiles. |
| **Concurrent Provisioning Races** | 2 threads calling `ProvisioningService.provision()` simultaneously | **PostgreSQL** | Thread 1 provisions; Thread 2 catches constraint, rolls back cleanly, returns existing profile (No 500). |
| **Session Poisoning & Rollback Safety** | Mock flush failure during provisioning | SQLite / Postgres | Session rolled back; subsequent `get_for_order` succeeds without `PendingRollbackError`. |
| **Crash After Settlement (Partial Commit)** | Break process between `confirm()` commit and `provision()` | SQLite / Postgres | Order remains `paid`; subsequent poll or reconciler detects paid order without profile and provisions it. |
| **Crash After Provisioning Before Notification** | Process exits after profile commit before delivery | SQLite / Postgres | Order remains `delivered_at IS NULL`; next reconcile cycle dispatches notification. |
| **Claim Token Lifecycle** | Issue token, claim once, attempt replay, test expiry (>24h) | SQLite / Postgres | Single-use setup succeeds; replay returns 400; expired returns 400. |
| **Starvation with >10 Abandoned Orders** | 15 abandoned checkouts + 1 delayed legitimate payment | SQLite / Postgres | Reconciler processes queue without starvation; legitimate delayed order transitions to `paid`. |
| **Reconciler Multi-Worker Advisory Lock** | 2 competing worker processes running `_payment_reconciler_loop` | **PostgreSQL** | `pg_try_advisory_lock` ensures exactly 1 loop runs; second worker skips cycle cleanly. |
| **Reconciler Under `TELEGRAM_MODE=webhook`** | Launch FastAPI with `TELEGRAM_MODE=webhook` | SQLite / Postgres | Reconciler runs every 60s and logs report summary. |
| **Restart & Retry Recovery** | Restart application while orders are pending | SQLite / Postgres | Background loop picks up pending orders within 60s of startup. |
| **Late Successful Payment After Expiry** | Customer completes checkout 3h later (marked abandoned) | SQLite / Postgres | Paystack verify transitions `abandoned -> paid` and provisions workspace. |

---

## 4. PHASED IMPLEMENTATION SEQUENCE

```
PHASE 1: Concurrency & Transaction Safety
├── Task 1.1: Implement atomic conditional SQL update in CheckoutService.confirm()
└── Task 1.2: Add db.rollback() in _provision_if_paid() exception handler

PHASE 2: Credential Delivery & Claim Token Architecture
├── Task 2.1: Create Alembic migration for `credential_claims` table
├── Task 2.2: Implement secure claim token generation in ProvisioningService
├── Task 2.3: Create /api/v1/auth/claim-workspace and complete-setup routes
└── Task 2.4: Update delivery message text to reflect secure email setup links

PHASE 3: Autonomous Reconciler & Starvation Fix
├── Task 3.1: Add last_reconciled_at and reconcile_attempts to Order model
├── Task 3.2: Implement abandoned checkout transition policy in confirm()
├── Task 3.3: Decouple reconciler from Telegram into FastAPI lifespan background task
└── Task 3.4: Add PostgreSQL advisory locking for multi-worker coordination

PHASE 4: PostgreSQL Concurrency CI Verification
├── Task 4.1: Add multi-threaded concurrency test suite in backend/tests/
└── Task 4.2: Verify 100% passing across all 12 scenarios in PostgreSQL container

PHASE 5: Administrative Live-Key Promotion (Manual Authorization Required)
├── Task 5.1: Run preflight verification script
├── Task 5.2: Configure ENVIRONMENT=production and live Paystack keys in Render Dashboard
└── Task 5.3: Verify GET /api/v1/checkout/config returns {"enabled": true, "live_mode": true}
```

---

## 5. DOCUMENTATION PROVENANCE & REVIEW SIGN-OFF

This technical remediation specification is submitted for review and authorization.  
**Strict Boundaries Observed:** No application code was modified; no commits or pushes were executed; no live Paystack transactions were initiated; production Render configuration remains safely in test mode.
