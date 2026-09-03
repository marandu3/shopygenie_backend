"""Development/demo seed data (MASTER PROMPT §83).

Idempotent — safe to re-run. Creates:
  - all permissions + system roles
  - the platform owner account (from .env — never hardcode real creds here)
  - one demo organization with a branch, register, tenant owner, a cashier,
    a supplier, a category, a couple of products, a customer, and one sample
    credit sale (created through the real create_sale service, not faked).

Run with:  python -m scripts.seed
"""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.core.permissions import ALL_PERMISSIONS, SYSTEM_ROLE_PERMISSIONS
from app.core.security import hash_password
from app.db.base import AsyncSessionLocal
from app.models.billing import BillingPlanConfig
from app.models.customer import Customer
from app.models.inventory import InventoryMovement, MovementType
from app.models.organization import Branch, Organization, Register, SubscriptionPlan, SubscriptionStatus
from app.models.product import Category, Product
from app.models.supplier import Supplier
from app.models.user import Permission, Role, RolePermission, User, WorkerStatus
from app.schemas.sale import PaymentIn, SaleCreate, SaleItemIn
from app.services.sales import create_sale

settings = get_settings()


async def seed_permissions_and_roles(db) -> dict[str, Role]:
    code_to_permission: dict[str, Permission] = {}
    for code in ALL_PERMISSIONS:
        result = await db.execute(select(Permission).where(Permission.code == code))
        permission = result.scalar_one_or_none()
        if permission is None:
            permission = Permission(code=code, description=code.replace(".", " ").replace("_", " ").title())
            db.add(permission)
            await db.flush()
        code_to_permission[code] = permission

    roles: dict[str, Role] = {}
    for role_name, permission_codes in SYSTEM_ROLE_PERMISSIONS.items():
        result = await db.execute(select(Role).where(Role.organization_id.is_(None), Role.name == role_name))
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(organization_id=None, name=role_name, is_system=True)
            db.add(role)
            await db.flush()

        # Reconcile permissions even for a role that already existed — this
        # is what lets a newly-added permission (e.g. a new module shipped
        # later) reach roles seeded by an earlier run, without ever removing
        # a permission a tenant may have customized by hand.
        existing_result = await db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == role.id))
        existing_permission_ids = {row[0] for row in existing_result.all()}
        for code in permission_codes:
            permission = code_to_permission[code]
            if permission.id not in existing_permission_ids:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        await db.flush()
        roles[role_name] = role

    return roles


async def seed_platform_owner(db) -> User:
    result = await db.execute(select(User).where(User.email == settings.platform_owner_email.lower()))
    owner = result.scalar_one_or_none()
    if owner is None:
        owner = User(
            organization_id=None,
            full_name=settings.platform_owner_name,
            email=settings.platform_owner_email.lower(),
            hashed_password=hash_password(settings.platform_owner_password),
            is_platform_owner=True,
            status=WorkerStatus.ACTIVE,
            must_change_password=False,
        )
        db.add(owner)
        await db.flush()
        print(f"Created platform owner: {owner.email}")
    else:
        print(f"Platform owner already exists: {owner.email}")
    return owner


async def seed_demo_tenant(db, roles: dict[str, Role]) -> None:
    result = await db.execute(select(Organization).where(Organization.slug == "demo-shop"))
    org = result.scalar_one_or_none()
    if org is not None:
        print("Demo organization already exists — skipping tenant seed")
        return

    org = Organization(
        name="Demo Retail Shop",
        slug="demo-shop",
        currency="TZS",
        tax_rate_percent=Decimal("18"),
        subscription_status=SubscriptionStatus.TRIAL,
    )
    db.add(org)
    await db.flush()

    branch = Branch(organization_id=org.id, name="Main Branch", address="Dar es Salaam")
    db.add(branch)
    await db.flush()

    register = Register(organization_id=org.id, branch_id=branch.id, name="Register 1", code="REG-01")
    db.add(register)

    owner = User(
        organization_id=org.id,
        branch_id=branch.id,
        role_id=roles["Tenant Owner"].id,
        full_name="Demo Owner",
        email="owner@demo-shop.co.tz",
        hashed_password=hash_password("DemoOwner123!"),
        status=WorkerStatus.ACTIVE,
        must_change_password=False,
    )
    db.add(owner)

    cashier = User(
        organization_id=org.id,
        branch_id=branch.id,
        register_id=register.id,
        role_id=roles["Cashier"].id,
        full_name="Demo Cashier",
        email="cashier@demo-shop.co.tz",
        hashed_password=hash_password("DemoCashier123!"),
        status=WorkerStatus.ACTIVE,
        must_change_password=False,
    )
    db.add(cashier)
    await db.flush()

    category = Category(organization_id=org.id, name="General")
    db.add(category)

    supplier = Supplier(organization_id=org.id, name="Demo Supplier Co.", phone="+255700000000")
    db.add(supplier)
    await db.flush()

    products = [
        Product(
            organization_id=org.id, category_id=category.id, supplier_id=supplier.id,
            name="Cooking Oil 1L", sku="SKU-001", unit="bottle",
            cost_price=Decimal("4500"), selling_price=Decimal("5500"),
            current_stock=50, low_stock_alert=10,
        ),
        Product(
            organization_id=org.id, category_id=category.id, supplier_id=supplier.id,
            name="Maize Flour 2kg", sku="SKU-002", unit="bag",
            cost_price=Decimal("3200"), selling_price=Decimal("4000"),
            current_stock=30, low_stock_alert=5,
        ),
        Product(
            organization_id=org.id, category_id=category.id, supplier_id=supplier.id,
            name="Bar Soap", sku="SKU-003", unit="pcs",
            cost_price=Decimal("800"), selling_price=Decimal("1200"),
            current_stock=100, low_stock_alert=20,
        ),
    ]
    db.add_all(products)
    await db.flush()

    for p in products:
        db.add(
            InventoryMovement(
                organization_id=org.id, product_id=p.id, movement_type=MovementType.OPENING_BALANCE,
                quantity=p.current_stock, previous_quantity=0, resulting_quantity=p.current_stock,
                reference_type="product_created", performed_by=owner.id, created_at=datetime.now(timezone.utc),
            )
        )
    await db.flush()

    customer = Customer(organization_id=org.id, name="Jane Walk-in", phone="+255711111111", credit_limit=Decimal("50000"))
    db.add(customer)
    await db.flush()

    # One real sample sale, run through the authoritative service so it
    # exercises the exact same stock/debt/audit logic production traffic does.
    sale_payload = SaleCreate(
        customer_id=customer.id,
        branch_id=branch.id,
        register_id=register.id,
        items=[SaleItemIn(product_id=products[0].id, quantity=2), SaleItemIn(product_id=products[2].id, quantity=3)],
        payments=[PaymentIn(amount=5000, method="CASH")],
        allow_credit=True,
    )
    await create_sale(db, organization_id=org.id, cashier_id=cashier.id, payload=sale_payload)

    print(f"Created demo organization '{org.name}' (slug={org.slug})")
    print(f"  Tenant owner login: {owner.email} / DemoOwner123!")
    print(f"  Cashier login:      {cashier.email} / DemoCashier123!")


async def seed_demo_tenant_sms_config(db) -> None:
    """Local-dev convenience: if real SMSGate credentials are set in .env,
    apply them to the demo tenant so SMS can be tested end to end without
    clicking through Settings > Notifications first. Runs every time (not
    just on first seed) so re-running after editing .env picks up the new
    values. Never touches any other organization — the live send path
    (app/integrations/sms/factory.py) only ever reads per-tenant config."""
    if not (settings.smsgate_username and settings.smsgate_password):
        return

    result = await db.execute(select(Organization).where(Organization.slug == "demo-shop"))
    org = result.scalar_one_or_none()
    if org is None:
        return

    org.sms_base_url = settings.smsgate_base_url or org.sms_base_url
    org.sms_username = settings.smsgate_username
    org.sms_password_encrypted = encrypt_secret(settings.smsgate_password)
    org.sms_device_id = settings.smsgate_device_id or None
    org.sms_enabled = True
    await db.flush()
    print(f"Applied SMSGate config from .env to '{org.name}'")


async def seed_billing_plans(db) -> None:
    """MASTER PROMPT §61 — one editable catalog row per SubscriptionPlan
    code. Only creates missing rows; never overwrites a platform owner's
    edits on a re-run."""
    defaults = [
        dict(code=SubscriptionPlan.BASIC, display_name="Basic", description="For a single shop just getting started.",
             price_monthly=Decimal("15000"), max_branches=1, max_workers=3, whatsapp_quota_monthly=50, storage_quota_mb=200, sort_order=1),
        dict(code=SubscriptionPlan.PROFESSIONAL, display_name="Professional", description="Growing shops with a small team across a couple of branches.",
             price_monthly=Decimal("35000"), max_branches=3, max_workers=10, whatsapp_quota_monthly=200, storage_quota_mb=1000, sort_order=2),
        dict(code=SubscriptionPlan.BUSINESS, display_name="Business", description="Multi-branch businesses that need full analytics and transfers.",
             price_monthly=Decimal("75000"), max_branches=10, max_workers=30, whatsapp_quota_monthly=1000, storage_quota_mb=5000, sort_order=3),
        dict(code=SubscriptionPlan.ENTERPRISE, display_name="Enterprise", description="Unlimited scale, priority support.",
             price_monthly=Decimal("150000"), max_branches=None, max_workers=None, whatsapp_quota_monthly=None, storage_quota_mb=None, sort_order=4),
    ]
    for defaults_row in defaults:
        result = await db.execute(select(BillingPlanConfig).where(BillingPlanConfig.code == defaults_row["code"]))
        if result.scalar_one_or_none() is None:
            db.add(BillingPlanConfig(**defaults_row))
    await db.flush()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        roles = await seed_permissions_and_roles(db)
        await seed_platform_owner(db)
        await seed_demo_tenant(db, roles)
        await seed_demo_tenant_sms_config(db)
        await seed_billing_plans(db)
        await db.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
