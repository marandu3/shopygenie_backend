# Production Readiness Checklist

Run through this before pointing real users at a deployment (MASTER PROMPT §108).

## Secrets & configuration

- [ ] `JWT_SECRET_KEY` is a real random 32+ character value (not a default from `.env.example`) — the app refuses to boot in production otherwise (`app/main.py`)
- [ ] `ENVIRONMENT=production` is set (activates the startup guards below)
- [ ] `CORS_ORIGINS` lists only the real deployed frontend origin(s) — no `*`
- [ ] `DATABASE_URL` uses `postgresql+asyncpg://` and points at the production database, not local/dev
- [ ] `PLATFORM_OWNER_EMAIL` / `PLATFORM_OWNER_PASSWORD` are real, strong values set via the hosting platform's secret store — never committed to Git
- [ ] `.env` is not committed (check `git status` — `.env.example` only)
- [ ] No secrets appear in Docker image layers (`docker history <image>` — should show no `ENV`/`ARG` with real values)

## Transport & access

- [ ] HTTPS is terminated in front of the backend (Render does this automatically)
- [ ] `/health` and `/health/ready` respond correctly post-deploy and expose no internal details
- [ ] Frontend's `environment.prod.ts` points at the real backend URL, not a placeholder

## Application behavior

- [ ] Debug mode is off — FastAPI's `/docs` is fine to leave enabled (no secrets exposed there) but confirm no stack traces leak to clients (`app/core/exceptions.py` handlers)
- [ ] Login rate limiting is active (`app/core/rate_limit.py` — in-memory, single-process; see note below)
- [ ] Account lockout after repeated failed logins is active (`app/services/auth.py`)
- [ ] Migrations are applied (`alembic upgrade head`) before traffic is routed to the new instance
- [ ] `scripts/seed.py` has been run at least once (bootstraps permissions, the platform owner, and the four billing-plan catalog rows)

## Known limitation to design around

- The login rate limiter is in-memory and per-process. If the backend ever
  runs as more than one process/instance behind a load balancer, each
  instance tracks its own counts — an attacker distributing requests across
  instances gets a higher effective limit than intended. Fine for a single
  instance; move to a shared store (Redis) before scaling horizontally.

## Verification

- [ ] `curl https://<backend>/health` → `{"status":"ok"}`
- [ ] `curl https://<backend>/health/ready` → `{"status":"ready"}` (confirms DB connectivity)
- [ ] Log in through the real frontend against the real backend
- [ ] Create a sale, confirm it appears in reports
- [ ] Confirm a cross-tenant request (different org's JWT) cannot read this org's data — the automated suite covers this (`tests/test_tenant_isolation.py`), but a manual spot-check before go-live is cheap insurance
