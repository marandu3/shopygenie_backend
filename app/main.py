from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, customers, debts, expenses, organizations, platform, products, purchases, reports, sales, suppliers, workers
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging

settings = get_settings()
configure_logging()

app = FastAPI(title="ShopyGenie API", version="2.0.0")

register_exception_handlers(app)

app.add_middleware(RequestLoggingMiddleware)

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
app.include_router(customers.router, prefix=API_PREFIX)
app.include_router(suppliers.router, prefix=API_PREFIX)
app.include_router(sales.router, prefix=API_PREFIX)
app.include_router(purchases.router, prefix=API_PREFIX)
app.include_router(debts.router, prefix=API_PREFIX)
app.include_router(expenses.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(platform.router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {"message": "ShopyGenie API", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}
