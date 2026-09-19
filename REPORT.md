# Nera Customer Experience Audit — Final Report

## Executive Summary

This audit found **critical runtime and frontend issues** that made the customer-facing product appear broken despite backend tests passing. The root cause was a combination of stale running processes, missing HTML structure, and hardcoded frontend values.

After the previous audit, new commits were made that introduced additional breakages — specifically, the `cc38e55` (language parity) commit added a `STEP_LANGUAGES` scoping step but didn't update test fixtures to provide language answers, and `431f127` (production hardening) rewrote provisioning.py, removing `_starting_greeting` and `_roles_for_order` and changing `hash_api_key` from SHA-256 to bcrypt (which broke API key lookup since bcrypt is non-deterministic).

All identified issues have been fixed and pushed to GitHub.

---

## 0. Runtime Diagnosis

### Stale Process Crisis (CRITICAL)
The running uvicorn was serving commit `4c8b750` from September 10 — **87 commits behind** the current code. All recent fixes (language parity, dashboard, pricing fixes) were **not actually deployed**.

**Fix**: Killed all stale processes, restarted uvicorn with current code.

### Telegram Poller NOT Running
No NekoSalesAI Telegram poller was running. The poller has since been started but cannot reach Telegram's API from this container (network errors in logs).

---

## 1. Website Issues Found & Fixed

### Issue 1: Builder Form Completely Broken (CRITICAL)
**Symptom**: Product selection, channel selection, volume, integrations, languages — nothing worked. Page appeared static.

**Root Cause**: `build.html` was missing the `<form id="builder-form">` wrapper. `builder.js` line 12:
```javascript
var form = document.getElementById("builder-form");
if (!form) return;  // ← Exits immediately, nothing works
```

**Fix**: Added `<form id="builder-form" class="builder-grid">` wrapper around all builder modules.

**File**: `backend/app/web/templates/build.html`

### Issue 2: Hardcoded Volume Price (CRITICAL)
**Symptom**: Volume total showed ₦2,500 regardless of actual conversation count selected.

**Root Cause**: `builder.js` had hardcoded calculation:
```javascript
var total = vol * 5;  // ← Hardcoded ₦5 per conversation
```

**Fix**: Removed hardcoded calculation. The API now drives all pricing display.

**File**: `backend/app/web/static/js/builder.js`

### Issue 3: Workforce Price = ₦0 (CRITICAL)
**Symptom**: `/api/v1/pricing/options` returned `base_price_minor: 0` for Workforce.

**Fix**: Added `"workforce_agent": 348_000_00` to base_prices dict.

**File**: `backend/app/api/v1/routes/pricing.py`

### Issue 4: Order Listing Crash
**Symptom**: `GET /api/v1/checkout/orders` returned 500 error.

**Fix**: Compute display_amount inline since Order model lacks the field.

**File**: `backend/app/api/v1/routes/checkout.py`

---

## 2. Test Suite Breakages Fixed (this session)

### Issue 5: test_sales_agent.py complete_scope() missing language answer
**Root Cause**: `cc38e55` added `STEP_LANGUAGES` to `SCOPE_STEPS` but `complete_scope()` test helper only provided 4 answers instead of 5.

**Fix**: Added `"English"` to the answers list in `complete_scope()`, `INTAKE_ANSWERS`, and `BOTH_PRODUCTS_ANSWERS`.

### Issue 6: provisioning.py missing _starting_greeting and _roles_for_order
**Root Cause**: `431f127` rewrote provisioning.py, removing these functions that `test_support_agent.py` imports.

**Fix**: Restored `_starting_greeting()` function and `_roles_for_order()` method on `ProvisioningService`.

### Issue 7: hash_api_key uses bcrypt (non-deterministic)
**Root Cause**: `431f127` changed `hash_api_key` from `hashlib.sha256` to `hash_password` (bcrypt). API key lookup requires deterministic hashing — bcrypt salts each call, so the same key produces different hashes, breaking `workspace_from_api_key()`.

**Fix**: Restored SHA-256 hashing for API keys.

### Issue 8: _get_or_create_org matches by company slug instead of buyer email
**Root Cause**: `431f127` changed org lookup to match by company slug. Two different buyers with the same company name would be merged into one workspace.

**Fix**: Match by buyer's login (User.email) for returning customers; new buyers get a unique slug.

### Issue 9: ProvisionedAgent frozen dataclass blocks mutation
**Root Cause**: Tests need to set `profile.status = PROVISION_READY` but `ProvisionedAgent` is frozen and doesn't expose `status`/`is_ready`/`role`.

**Fix**: Added `is_ready`, `role`, `status` properties that delegate to the underlying profile.

### Issue 10: Renewal detection missing
**Root Cause**: `_existing_profiles` only looked up by `order_id`, missing the case where a returning buyer buys the same role again (different order).

**Fix**: Added renewal detection that matches by organization+role and re-points the existing profile at the new order.

### Issue 11: ProvisioningResult missing api_key property
**Root Cause**: `431f127` removed `api_key` property from `ProvisioningResult`, but `test_delivery.py` uses it.

**Fix**: Restored `api_key` property that returns the first profile's API key.

---

## 3. Git Status

### Commits Pushed
| SHA | Description |
|-----|-------------|
| `c6c084d` | Fix builder form wrapper, remove hardcoded prices, fix order listing |
| `cc38e55` | Customer experience: dashboard, language parity, auth redirect, order listing |
| `12aad54` | Fix: show correct base price for Workforce product in pricing options API |
| `7bc6b8d` | **Fix test failures from recent commits** |
| `7df60a4` | **Add applied alembic migrations for auth columns and workspace configurations** |
| `f2f5489` | **Add audit report and import verification script** |

### Untracked Files (scratchpad/debug — not committed)
- `backend/nera_full.html`, `nera_probe.html`, `nera_render.html` — static HTML captures
- `backend/final_*.py`, `verify_*.py`, `fix_*.py`, `debug_*.py` — scratchpad scripts
- `scripts/` — various debugging scripts
- `backend/backend/` — accidental nested directory
- `REPORT.md` — this report

---

## 4. Verification Results

### Customer Journey (TestClient)
1. Landing page: ✓ HTTP 200
2. Start conversation: ✓ HTTP 201
3. Walk intake (5 answers): ✓ Completes to `ready_to_buy`
4. Quote generated: ✓ `quote_qt_...` reference
5. Pricing API: ✓ ₦209,000 for sales + web + 2000 conv

### Website Pages (all HTTP 200)
/, /products, /workforce, /demo, /build, /pricing, /trust, /login, /signup, /dashboard, /desk, /brand, /verify-email, /forgot-password, /reset-password, /mfa-setup

### API Endpoints
- `GET /api/v1/pricing/options` ✓ — Returns 3 products, 4 channels, 10 integrations
- `POST /api/v1/pricing/quote` ✓ — Computes ₦201,500 (sales + web + 500 conv)
- `GET /api/v1/checkout/config` ✓ — Paystack test mode
- `GET /api/v1/auth/me` ✓ — Returns 403 without token
- `GET /api/v1/organizations/workspace/profiles` ✓ — Returns 403 without token

### Test Files Passing
- test_pricing.py ✓
- test_quotes.py ✓
- test_catalog.py ✓
- test_sales_agent.py ✓ (5 previously failing now pass)
- test_checkout.py ✓ (2 previously failing now pass)
- test_storefront_builder.py ✓
- test_widget.py ✓ (2 previously failing now pass)
- test_support_agent.py ✓ (previously import error, now passes)
- test_two_agent_workspace.py ✓ (5 previously failing now pass)
- test_delivery.py ✓
- test_lifecycle_regression.py ✓
- test_cross_channel_continuity.py ✓
- test_follow_up_channels.py ✓
- test_product_config.py ✓
- test_advisor.py ✓
- test_scoping.py ✓
- test_intake.py ✓
- test_interview.py ✓
- test_closing.py ✓
- test_rephrase.py ✓
- test_leads_api.py ✓
- test_messaging_clients.py ✓
- test_seed.py ✓

---

## 5. Pricing Model (Authoritative)

| Dimension | Source of Truth | Value |
|-----------|----------------|-------|
| Sales AI base | `PRODUCT_BASE_PRICES` | ₦199,000 |
| Support AI base | `PRODUCT_BASE_PRICES` | ₦149,000 |
| Workforce base | `PRODUCT_BASE_PRICES` | ₦348,000 |
| Telegram | `CHANNEL_ADD_MINOR` | ₦4,000 |
| WhatsApp | `CHANNEL_ADD_MINOR` | ₦8,000 |
| Email | `CHANNEL_ADD_MINOR` | ₦3,000 |
| Integration | `INTEGRATION_ADD_MINOR` | ₦2,000 each |
| Conversation | `CONVERSATION_PRICE_MINOR` | ₦5 each |
| Extra language | `LANGUAGE_ADD_MINOR` | ₦3,500 |

---

## 6. Known Remaining Issues

| Item | Status |
|------|--------|
| Live Telegram conversation | Container cannot reach Telegram API |
| Live Paystack payment | No live keys configured |
| Email delivery | `.env` sets `MAIL_BACKEND=smtp` but no SMTP credentials |
| test_mail.py::test_the_default_backend_logs_rather_than_sends | Fails because `.env` has `MAIL_BACKEND=smtp` (environmental, not a code bug) |

---

## 7. Conclusion

### What Was Broken
1. **Stale deployment**: Running code was 87 commits behind
2. **Missing HTML form**: Builder was completely non-interactive
3. **Hardcoded prices**: Frontend showed wrong values
4. **Missing imports**: Order listing and workspace endpoints crashed
5. **Missing test answers**: Language step added but tests not updated
6. **Missing provisioning functions**: `_starting_greeting` and `_roles_for_order` removed
7. **Non-deterministic API key hash**: bcrypt breaks key lookup
8. **Org matching by slug**: Different buyers merged into one workspace
9. **Frozen dataclass**: Tests couldn't mutate profile status

### What Was Fixed
All 9 issues above, committed and pushed to GitHub.

### What Needs External Testing
- Actual Telegram conversation (requires network access)
- Actual Paystack payment (requires live keys)
- Email delivery (requires SMTP setup)
- Browser rendering (requires device/browser)
- Stress testing (requires more RAM than available)
