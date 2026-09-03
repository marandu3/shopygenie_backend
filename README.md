# ShopyGenie Backend

Multi-tenant Point-of-Sale (POS) SaaS platform API — FastAPI + PostgreSQL.
Powers sales, inventory (with FIFO costing), purchases, customers/debts,
expenses, branch transfers, reporting, billing/usage metering, and
platform-owner administration for every tenant business running on
ShopyGenie.

The companion Angular app lives in the sibling `shopygenie_frontend`
repository. This README covers the backend only; see that repo's own
`README.md` for the UI, and `DEPLOYMENT.md` (in both repos) for Docker and
production (Render/Netlify) deployment.

---

## 1. Tech stack

| Layer | Choice |
|---|---|
| Framework | FastAPI 0.117 (async) |
| ORM | SQLAlchemy 2.0 (async engine, `asyncpg` driver) |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | JWT access + refresh tokens (`python-jose`), `passlib`/`bcrypt` password hashing |
| Money | `Decimal` + `Numeric(14,2)` everywhere — never `float` for persisted/authoritative arithmetic |
| Testing | `pytest` + `pytest-asyncio` |

## 2. Architecture at a glance

- **Multi-tenancy.** Every tenant-scoped row carries an `organization_id`.
  `AuthContext.organization_id` resolves to `acting_organization_id or
  user.organization_id` on every request — the `acting_organization_id`
  ("act_org" JWT claim) is minted only by
  `POST /platform/organizations/{id}/enter` and only honored for users with
  `is_platform_owner = true`. This is how a platform owner can inspect a
  tenant's data without a second login, while every ordinary tenant user is
  hard-locked to their own organization.
- **RBAC.** Permissions are checked by **code**, never by role name
  (`app/core/permissions.py` — see `SYSTEM_ROLE_PERMISSIONS`). Endpoints
  declare a required permission via the `require_permission(...)` FastAPI
  dependency; `require_tenant_context` / `require_platform_owner` cover the
  other two access shapes.
- **FIFO inventory costing.** Every unit received (purchase, opening
  balance, stock adjustment, a voided sale) creates an `InventoryCostLayer`.
  Every unit sold consumes the oldest remaining layers first
  (`app/services/inventory_costing.py`), so COGS and gross-profit reports
  reflect real historical cost — not today's price. Falls back to
  `product.cost_price` gracefully when no layers exist yet (older/seed
  data).
- **Approval workflows.** Discounts above an organization's configured
  threshold, and sales that push a customer over their credit limit, both
  require a named approver — a specific user with the right permission,
  validated server-side (`_validate_approver` in `app/services/sales.py`).
  This is not a client-side checkbox; the API rejects the sale with
  `422 VALIDATION_ERROR` if the named approver doesn't hold the permission.
- **Held sales, branch transfers, tenant account requests, platform-owner
  invitations, usage metering, expense evidence uploads, and the ad-hoc
  report builder** are all server-backed (not localStorage) — see
  `app/api/v1/held_sales.py`, `transfers.py`, `account_requests.py`,
  `platform_owner_invitations.py`, `billing.py` (`/billing/usage`),
  `expenses.py` (`/expenses/{id}/evidence`), and `reports.py`
  (`/reports/builder`) respectively.

## 3. Project layout

```
app/
  api/v1/        FastAPI routers — one file per resource area
  core/          config, security (JWT/hashing), permissions, exceptions
  db/            session/engine setup
  integrations/  SMS gateway adapter (stub by default)
  models/        SQLAlchemy models
  schemas/       Pydantic request/response schemas
  services/      business logic (kept out of the API layer)
alembic/         migrations (script_location)
scripts/seed.py  idempotent: permissions, system roles, platform owner
tests/           pytest suite
```

## 4. Running locally (native — recommended for active development)

### Prerequisites

- Python 3.12
- PostgreSQL 16 reachable somewhere (a local install, or the Dockerized
  Postgres from `DEPLOYMENT.md` §1 — both work fine here)
- Git

### Steps

```bash
git clone <backend-repo-url> shopygenie_backend
cd shopygenie_backend

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# then edit .env — see the table below
```

`.env` variables (full annotated list in `.env.example`):

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@host:port/dbname` — note the `+asyncpg` driver suffix, this is not a plain `postgresql://` URL |
| `JWT_SECRET_KEY` | Yes | 32+ random characters. Refuses to boot in production with a default/short value. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CORS_ORIGINS` | Yes | Comma-separated origins allowed to call the API. `http://localhost:4200` for local frontend dev |
| `PLATFORM_OWNER_EMAIL` / `PLATFORM_OWNER_PASSWORD` / `PLATFORM_OWNER_NAME` | Yes | Bootstraps the one initial platform-owner account, via `scripts/seed.py`. Idempotent — running the seed again doesn't reset the password |
| `SMSGATE_BASE_URL` / `SMSGATE_USERNAME` / `SMSGATE_PASSWORD` / `SMSGATE_DEVICE_ID` | No | Local-dev/seed convenience only — applied to the demo tenant by `scripts/seed.py`. Leave blank to use the console-logging SMS stub. Real tenants configure SMSGate per-organization in Settings → Notifications (never a global credential) |
| `UPLOADS_DIR` / `MAX_UPLOAD_BYTES` | No | Defaults: `uploads`, 5MB. Where expense-evidence files are stored on disk |
| `ENVIRONMENT` | No | `development` locally; `production` only for a real deployment (activates stricter startup checks) |

```bash
# Create/update the schema
alembic upgrade head

# Seed permissions, system roles, and the platform-owner account
python -m scripts.seed

# Run the API with auto-reload
uvicorn app.main:app --reload --port 8080
```

`8080` matches the frontend's default `apiUrl` in
`shopygenie_frontend/src/environments/environment.ts` — use this port for
local dev unless you also change that file.

Verify: `curl http://localhost:8080/health` → `{"status":"ok"}`.
Interactive API docs (Swagger UI): `http://localhost:8080/docs`.

Log in as the platform owner with the email/password from `.env`, or point
the frontend (`shopygenie_frontend`, default `http://localhost:4200`) at
this backend and log in through the UI.

### Running with Docker instead

See `DEPLOYMENT.md` §1 for the full Docker Compose flow (backend +
Postgres + frontend, all three containers, one command:
`docker compose up --build`). Most of this project's own development used
the native flow above against a Dockerized Postgres only, for faster
reload iteration — that hybrid works too:

```bash
docker compose up -d postgres   # from the compose file, Postgres only
# then the native steps above, pointing DATABASE_URL at localhost:5433
```

## 5. Running the test suite

```bash
pytest -q
```

58 tests as of this writing, covering auth/permissions, sales (incl. FIFO
costing and discount/credit approval thresholds), purchases and returns,
shifts, debts, reconciliation, held sales, branch transfers, account
requests, platform-owner invitations, expense evidence, and the report
builder. Tests run against the same `DATABASE_URL` configured in `.env` —
they create and clean up their own data (unique emails per run via
`uuid.uuid4().hex[:8]` suffixes), not an isolated throwaway database, so
don't point `DATABASE_URL` at a database you can't afford to have test rows
appear in temporarily.

## 6. Database migrations

```bash
# After changing a model in app/models/:
alembic revision --autogenerate -m "describe the change"

# Always read the generated file before applying — autogenerate is good
# but not infallible, especially around renamed/dropped columns.

alembic upgrade head        # apply
alembic downgrade -1        # roll back one (use with care)
alembic current             # what revision is the DB actually on
alembic history              # full migration chain
```

## 7. Key concepts worth knowing before touching this codebase

- **Money is always `Decimal`.** Use the shared `money()` helper
  (ROUND_HALF_UP, 2 decimal places) for any rounding — never round manually
  and never let a `float` touch a persisted money field.
- **`ValidationAppError` → HTTP 422**, not 400. This is a deliberate
  project convention; tests assert `== 422`.
- **`Customer.credit_limit == 0` means "no limit configured"**, not "zero
  credit" — preserved for backward compatibility with existing data.
- **Permission checks are always by code** (`"transfers.approve"`, not
  `role_name == "Manager"`). If you add a new protected action, add a new
  permission code in `app/core/permissions.py` and wire it into the
  relevant `SYSTEM_ROLE_PERMISSIONS` entries, then use
  `Depends(require_permission(YOUR_NEW_CODE))` on the endpoint.
- **Branch transfers track logistics, not stock pools.** This schema has no
  per-branch stock quantity split (`Product.current_stock` is
  organization-wide), so a transfer's `REQUESTED → APPROVED → IN_TRANSIT →
  RECEIVED/COMPLETED` lifecycle is audited tracking of physical movement,
  not an automatic stock mutation between branches. Worth knowing before
  assuming it does more than it does.
- **Usage metering only counts what's real.** `app/services/usage.py`
  currently increments on one real event (SMS sent on worker invite). It
  deliberately does not fabricate metrics for channels this codebase
  doesn't actually have (WhatsApp, storage, etc.) — extend it the same way
  when a new metered feature ships for real.
