import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import SUPPLIERS_MANAGE
from app.db.session import get_db
from app.models.supplier import Supplier
from app.schemas.customer import SupplierCreate, SupplierOut, SupplierUpdate

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.post("", response_model=SupplierOut, status_code=201)
async def create_supplier(
    payload: SupplierCreate,
    ctx: AuthContext = Depends(require_permission(SUPPLIERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    supplier = Supplier(organization_id=org_id, **payload.model_dump())
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


@router.get("", response_model=list[SupplierOut])
async def list_suppliers(
    ctx: AuthContext = Depends(require_permission(SUPPLIERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(select(Supplier).where(Supplier.organization_id == org_id).order_by(Supplier.name))
    return list(result.scalars())


@router.put("/{supplier_id}", response_model=SupplierOut)
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
    ctx: AuthContext = Depends(require_permission(SUPPLIERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    supplier = await db.get(Supplier, supplier_id)
    if supplier is None or supplier.organization_id != org_id:
        raise NotFoundError("Supplier not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)

    await db.commit()
    await db.refresh(supplier)
    return supplier
