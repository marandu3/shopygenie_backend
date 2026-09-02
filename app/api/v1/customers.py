import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import CUSTOMERS_CREATE, CUSTOMERS_UPDATE, CUSTOMERS_VIEW
from app.db.session import get_db
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.services.debts import customer_outstanding_balance, outstanding_balances_for_customers

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("", response_model=CustomerOut, status_code=201)
async def create_customer(
    payload: CustomerCreate,
    ctx: AuthContext = Depends(require_permission(CUSTOMERS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    customer = Customer(organization_id=org_id, **payload.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return CustomerOut.model_validate(customer, from_attributes=True)


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    ctx: AuthContext = Depends(require_permission(CUSTOMERS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(select(Customer).where(Customer.organization_id == org_id).order_by(Customer.name))
    customers = list(result.scalars())
    balances = await outstanding_balances_for_customers(db, organization_id=org_id, customer_ids=[c.id for c in customers])

    out = []
    for c in customers:
        item = CustomerOut.model_validate(c, from_attributes=True)
        item.outstanding_balance = float(balances.get(c.id, 0))
        out.append(item)
    return out


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(CUSTOMERS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != org_id:
        raise NotFoundError("Customer not found")

    item = CustomerOut.model_validate(customer, from_attributes=True)
    item.outstanding_balance = float(await customer_outstanding_balance(db, organization_id=org_id, customer_id=customer_id))
    return item


@router.put("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    ctx: AuthContext = Depends(require_permission(CUSTOMERS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != org_id:
        raise NotFoundError("Customer not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    await db.commit()
    await db.refresh(customer)
    item = CustomerOut.model_validate(customer, from_attributes=True)
    item.outstanding_balance = float(await customer_outstanding_balance(db, organization_id=org_id, customer_id=customer_id))
    return item
