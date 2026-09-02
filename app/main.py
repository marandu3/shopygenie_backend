from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import audit, auth, categories, customers, debts, expenses, organizations, platform, products, purchases, reconciliation, reports, sales, shifts, suppliers, workers
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.security_headers import SecurityHeadersMiddleware

settings = get_settings()
configure_logging()

_INSECURE_DEFAULT_SECRETS = {"your_secret_key_here", "change-me-to-a-long-random-value", "dev-only-secret-2f8a9c1e4b7d6f3a0c5e8b1d4f7a9c2e5b8d1f4a7c0e3b6d9f2a5c8e1b4d7f0a"}

if settings.is_production:
    # Fail loudly at startup rather than silently serving traffic with a
    # known/guessable JWT secret or an open CORS policy (MASTER PROMPT §85-86).
    if settings.jwt_secret_key in _INSECURE_DEFAULT_SECRETS or len(settings.jwt_secret_key) < 32:
        raise RuntimeError("JWT_SECRET_KEY is missing, a known default, or too short for production. Set a real random secret.")
    if "*" in settings.cors_origin_list:
        raise RuntimeError("CORS_ORIGINS must not include '*' in production.")

app = FastAPI(title="ShopyGenie API", version="2.0.0")

register_exception_handlers(app)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# No "*" with credentials — trusted origins only, from environment config
# (MASTER PROMPT §86). Configure CORS_ORIGINS in .env.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(organizations.router, prefix=API_PREFIX)
app.include_router(workers.router, prefix=API_PREFIX)
app.include_router(products.router, prefix=API_PREFIX)
app.include_router(categories.router, prefix=API_PREFIX)
app.include_router(customers.router, prefix=API_PREFIX)
app.include_router(suppliers.router, prefix=API_PREFIX)
app.include_router(sales.router, prefix=API_PREFIX)
app.include_router(purchases.router, prefix=API_PREFIX)
app.include_router(debts.router, prefix=API_PREFIX)
app.include_router(expenses.router, prefix=API_PREFIX)
app.include_router(shifts.router, prefix=API_PREFIX)
app.include_router(reconciliation.router, prefix=API_PREFIX)
app.include_router(audit.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(platform.router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {"message": "ShopyGenie API", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}
