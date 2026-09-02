import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models.inventory import InventoryMovement, MovementType
from app.models.organization import Branch, Organization, Register
from app.models.product import Category, Product
from app.models.supplier import Supplier
from app.models.user import Role, User, WorkerStatus
from scripts.seed import seed_permissions_and_roles

settings = get_settings()


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    """The login rate limiter is a module-level singleton (by design — see
    app/core/rate_limit.py) so it persists across this whole pytest session
    under one shared test-client IP, which would otherwise starve later
    tests. Reset before each test so tests stay independent of each other;
    test_account_locks_after_repeated_failed_logins is what actually
    exercises the limiter's real behavior."""
    login_rate_limiter._hits.clear()
    yield


@pytest_asyncio.fixture
async def db():
    """A fresh engine per test, bound to THAT test's event loop.

    pytest-asyncio gives each test function its own event loop by default;
    asyncpg connections are loop-bound, so sharing one module-level engine
    (as app.db.base does at runtime) across tests breaks on the second test.
    NullPool means every checkout opens a real connection and closes it
    again — no pooled connection ever outlives the test that created it.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        await seed_permissions_and_roles(session)
        await session.commit()

    async def override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    async with session_factory() as session:
        yield session

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class Tenant:
    def __init__(self, org_id, owner_email, owner_password, cashier_email, cashier_password, product_id, product2_id, customer_id):
        self.org_id = org_id
        self.owner_email = owner_email
        self.owner_password = owner_password
        self.cashier_email = cashier_email
        self.cashier_password = cashier_password
        self.product_id = product_id
        self.product2_id = product2_id
        self.customer_id = customer_id


@pytest_asyncio.fixture
async def tenant(db) -> Tenant:
    """Builds a fully isolated org (branch, roles, two products, one
    customer, an owner + cashier login) directly via the DB — mirrors
    scripts/seed.py but scoped to one test with unique identifiers."""
    suffix = uuid.uuid4().hex[:8]

    result = await db.execute(select(Role).where(Role.organization_id.is_(None)))
    roles = {r.name: r for r in result.scalars().all()}

    org = Organization(name=f"Test Shop {suffix}", slug=f"test-shop-{suffix}", tax_rate_percent=Decimal("0"))
    db.add(org)
    await db.flush()

    branch = Branch(organization_id=org.id, name="Main")
    db.add(branch)
    await db.flush()
    register = Register(organization_id=org.id, branch_id=branch.id, name="R1", code="R1")
    db.add(register)

    owner_password = "OwnerPass123!"
    owner = User(
        organization_id=org.id, branch_id=branch.id, role_id=roles["Tenant Owner"].id,
        full_name="Owner", email=f"owner-{suffix}@shopygenie-tests.dev",
        hashed_password=hash_password(owner_password), status=WorkerStatus.ACTIVE, must_change_password=False,
    )
    db.add(owner)

    cashier_password = "CashierPass123!"
    cashier = User(
        organization_id=org.id, branch_id=branch.id, role_id=roles["Cashier"].id,
        full_name="Cashier", email=f"cashier-{suffix}@shopygenie-tests.dev",
        hashed_password=hash_password(cashier_password), status=WorkerStatus.ACTIVE, must_change_password=False,
    )
    db.add(cashier)

    category = Category(organization_id=org.id, name="General")
    db.add(category)
    supplier = Supplier(organization_id=org.id, name="Supplier")
    db.add(supplier)
    await db.flush()

    product = Product(
        organization_id=org.id, category_id=category.id, supplier_id=supplier.id,
        name="Widget", sku=f"SKU-{suffix}-1", unit="pcs",
        cost_price=Decimal("100"), selling_price=Decimal("150"),
        current_stock=10, low_stock_alert=2,
    )
    product2 = Product(
        organization_id=org.id, category_id=category.id, supplier_id=supplier.id,
        name="Gadget", sku=f"SKU-{suffix}-2", unit="pcs",
        cost_price=Decimal("200"), selling_price=Decimal("300"),
        current_stock=5, low_stock_alert=1,
    )
    db.add_all([product, product2])
    await db.flush()

    for p in (product, product2):
        db.add(
            InventoryMovement(
                organization_id=org.id, product_id=p.id, movement_type=MovementType.OPENING_BALANCE,
                quantity=p.current_stock, previous_quantity=0, resulting_quantity=p.current_stock,
                reference_type="product_created", performed_by=owner.id, created_at=datetime.now(timezone.utc),
            )
        )
    await db.flush()

    from app.models.customer import Customer

    customer = Customer(organization_id=org.id, name="Test Customer", phone="+255700000000")
    db.add(customer)
    await db.flush()
    await db.commit()

    return Tenant(
        org_id=org.id,
        owner_email=owner.email, owner_password=owner_password,
        cashier_email=cashier.email, cashier_password=cashier_password,
        product_id=product.id, product2_id=product2.id, customer_id=customer.id,
    )


async def login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
