# NekoSalesAI — backend

FastAPI + SQLAlchemy. The product overview lives in the [root README](../README.md);
this file is about how the code is arranged and why.

---

## The one rule

**No claim outlives its feature.**

It is enforced mechanically for the storefront's own capabilities:
`app/catalog/products.py` gives every `Capability` a `verified_by` module path,
and `tests/test_catalog.py::test_every_capability_claim_points_at_real_code`
fails if the module stops importing. A feature cannot be deleted while the
landing page still advertises it.

Earlier versions of this file listed a Worker Runtime, Retry Engine, Dead Letter
Queue, Decision Engine, Recommendation Engine, Activity Feed and AI Task Engine
as complete. Commits `aa7037a`, `4e33612` and `77d471f` deleted all of it — it was
unreachable, and one router faked its own health check. The docs went stale
instead, which is the same failure the product exists to refuse. Do not
reintroduce it here.

---

## Layout

```
app/
  main.py          app construction, CORS, the widget's origin exception
  config/          settings and logging
  database/        engine, session, declarative base
  models/          12 tables
  schemas/         request and response shapes
  repositories/    query helpers, tenant-scoped
  auth/            JWT for humans, api_key.py for customer integrations
  catalog/         NekoSalesAI's own ProductConfig — the storefront
  products/        per-tenant config, intake, interview, tenant resolution
  pricing/         complexity pricing, quote issue and redemption
  sales/           the agent, reasoning record, approval gate, conversation service
  payments/        Paystack client, checkout, provisioning
  followups/       post-sale calendar, sender seam, cron runner
  mail/            transport (console/smtp/memory) and message composition
  api/v1/routes/   41 endpoints
  web/             Jinja templates, CSS, the storefront JS and the widget
```

---

## Decisions worth knowing before you change things

**The agent is deterministic, and that is load-bearing.** `compose_reply` in
`app/sales/agent.py` is pure — no database, no network, no clock. It reads the
message, picks a rule, and composes from config. That purity is what makes the
refusal to discount directly testable. If you add a model call, it goes *outside*
this function.

**Money is integer minor units.** Kobo, never floats. `format_money` renders;
nothing else formats amounts.

**Config arrives as an argument, never an import.** `resolve_config` decides whose
rules apply. There is deliberately **no fallback** from a customer's config to the
storefront's: a workspace with a missing config gets a minimal one that escalates
everything, because an agent quoting our prices to someone else's buyers is worse
than an agent that cannot answer.

**`role` is a column, not a config field.** `config_json` is written by customer
intake. A role stored there could be edited from `support_agent` to `sales_agent`,
promoting a support bot into one that quotes prices and takes money. What was
bought decides what the agent may do.

**The factory is a role, and it is not for sale.** There are three roles in
`app/products/config.py`: `sales_agent`, `support_agent`, and `builder` — Nera
itself. Nera does not sell for a business; it builds the AI that does, so it needs
a role of its own to introduce itself as the builder and to price a build. But
`BUILDABLE_ROLES` deliberately excludes it, and both the config loader
(`serialization.py`) and the tenant resolver (`resolver.py`) refuse a stored
`builder`, degrading to a role that can do less. A customer handed a builder could
provision workspaces, which is authority nobody buys.

**Two credentials, different powers.** `widget_token` is public — it ships in the
customer's page source and may only start a conversation. `X-API-Key` is secret,
verified against a stored SHA-256 hash (fast hash, not bcrypt: it is 24 bytes of
CSPRNG output checked on every request), narrowed by an indexed prefix, compared
in constant time.

**Provisioning is idempotent and inline.** The webhook and the browser return page
both call it, often in the same second. Two workspaces and two API keys for one
payment is the bug it guards against.

**Email failures are reported, not raised.** By the time a receipt is composed the
money has moved. A workspace that failed to save because its welcome email
bounced is strictly worse than a message to resend.

**A failed follow-up stays scheduled.** `UnconfiguredSender` raises rather than
silently succeeding, because a follow-up marked sent that nobody received is
worse than an obvious failure.

---

## Running

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./dev.sh                                  # migrate, seed, serve with reload
```

```bash
.venv/bin/python -m pytest tests/ -q      # 526 tests
node scripts/check_builder.js             # pricing builder under a stub DOM
node scripts/check_page.js                # landing page motion, reduced-motion paths
.venv/bin/python -m app.followups.runner --dry-run
.venv/bin/alembic upgrade head
```

The JS harnesses exist because the money-carrying paths live in the browser —
which request body gets posted, and which figure gets rendered. They stub the DOM
rather than driving a real one; layout is not covered.

---

## Configuration

Defaults are in `app/config/settings.py`. Safe out of the box, and loud about it:

- `SECRET_KEY` defaults to a published dev string; `main.py` warns at startup
  while it is still in place.
- `MAIL_BACKEND` defaults to `console` — logs instead of sending, so a fresh clone
  exercises every mail path and no test reaches a real inbox.
- `PAYSTACK_SECRET_KEY` is empty, which disables checkout and says why. A payment
  button that 500s is a worse failure.
- `GROQ_API_KEY` is empty and the rephrasing layer stays off.

---

## Tests

Every test runs against in-memory SQLite built from `Base.metadata`, never the
dev database. `get_db` is overridden so routes and assertions share one session.

Coverage is deliberately weighted toward things that cost money or trust:

| File | What it defends |
|---|---|
| `test_pricing.py` | every figure is derivable and itemised; ceilings refuse in prose |
| `test_catalog.py` | no claim outlives its feature; the agent cannot self-discount |
| `test_checkout.py` | a quoted price survives unchanged to the charge |
| `test_widget.py` | the public token cannot do what the secret key can; no cross-tenant reads |
| `test_mail.py` | a credential that cannot be reissued; a follow-up marked sent that nobody got |
| `test_sales_flow.py` | the whole path from first message to paid order |

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md). The short version: understand it before
changing it, extend rather than replace, and never commit knowingly broken code.
If you delete a feature, delete its claim in the same commit.
