import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.permissions import HELD_SALES_VIEW, SALES_CREATE
from app.db.session import get_db
from app.schemas.held_sale import HeldSaleCreate, HeldSaleOut
from app.services.held_sales import create_held_sale, discard_held_sale, get_held_sale, list_held_sales

router = APIRouter(prefix="/held-sales", tags=["Held Sales"])


@router.post("", response_model=HeldSaleOut, status_code=201)
async def create_held_sale_endpoint(
    payload: HeldSaleCreate,
    ctx: AuthContext = Depends(require_permission(SALES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    held = await create_held_sale(db, organization_id=org_id, cashier_id=ctx.user_id, payload=payload)
    await db.commit()
    return held


@router.get("", response_model=list[HeldSaleOut])
async def list_held_sales_endpoint(
    ctx: AuthContext = Depends(require_permission(HELD_SALES_VIEW)), db: AsyncSession = Depends(get_db)
):
    org_id = ctx.require_organization_id()
    return await list_held_sales(db, organization_id=org_id)


@router.get("/{held_sale_id}", response_model=HeldSaleOut)
async def get_held_sale_endpoint(
    held_sale_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(HELD_SALES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await get_held_sale(db, organization_id=org_id, held_sale_id=held_sale_id)


@router.delete("/{held_sale_id}", status_code=204)
async def discard_held_sale_endpoint(
    held_sale_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(SALES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    await discard_held_sale(db, organization_id=org_id, held_sale_id=held_sale_id)
    await db.commit()
