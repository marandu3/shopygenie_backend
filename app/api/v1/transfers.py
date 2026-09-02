import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.permissions import TRANSFERS_APPROVE, TRANSFERS_RECEIVE, TRANSFERS_REQUEST, TRANSFERS_VIEW
from app.db.session import get_db
from app.schemas.transfer import TransferCreate, TransferOut
from app.services.transfers import (
    approve_transfer,
    create_transfer,
    list_transfers,
    mark_in_transit,
    receive_transfer,
    reject_transfer,
)

router = APIRouter(prefix="/transfers", tags=["Inventory Transfers"])


class RejectTransferRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.post("", response_model=TransferOut, status_code=201)
async def create_transfer_endpoint(
    payload: TransferCreate, ctx: AuthContext = Depends(require_permission(TRANSFERS_REQUEST)), db: AsyncSession = Depends(get_db)
):
    org_id = ctx.require_organization_id()
    transfer = await create_transfer(db, organization_id=org_id, requested_by=ctx.user_id, payload=payload)
    await db.commit()
    return transfer


@router.get("", response_model=list[TransferOut])
async def list_transfers_endpoint(ctx: AuthContext = Depends(require_permission(TRANSFERS_VIEW)), db: AsyncSession = Depends(get_db)):
    org_id = ctx.require_organization_id()
    return await list_transfers(db, organization_id=org_id)


@router.post("/{transfer_id}/approve", response_model=TransferOut)
async def approve_transfer_endpoint(transfer_id: uuid.UUID, ctx: AuthContext = Depends(require_permission(TRANSFERS_APPROVE)), db: AsyncSession = Depends(get_db)):
    org_id = ctx.require_organization_id()
    transfer = await approve_transfer(db, organization_id=org_id, transfer_id=transfer_id, actor_id=ctx.user_id)
    await db.commit()
    return transfer


@router.post("/{transfer_id}/in-transit", response_model=TransferOut)
async def mark_in_transit_endpoint(transfer_id: uuid.UUID, ctx: AuthContext = Depends(require_permission(TRANSFERS_APPROVE)), db: AsyncSession = Depends(get_db)):
    org_id = ctx.require_organization_id()
    transfer = await mark_in_transit(db, organization_id=org_id, transfer_id=transfer_id, actor_id=ctx.user_id)
    await db.commit()
    return transfer


@router.post("/{transfer_id}/receive", response_model=TransferOut)
async def receive_transfer_endpoint(transfer_id: uuid.UUID, ctx: AuthContext = Depends(require_permission(TRANSFERS_RECEIVE)), db: AsyncSession = Depends(get_db)):
    org_id = ctx.require_organization_id()
    transfer = await receive_transfer(db, organization_id=org_id, transfer_id=transfer_id, actor_id=ctx.user_id)
    await db.commit()
    return transfer


@router.post("/{transfer_id}/reject", response_model=TransferOut)
async def reject_transfer_endpoint(
    transfer_id: uuid.UUID, payload: RejectTransferRequest, ctx: AuthContext = Depends(require_permission(TRANSFERS_APPROVE)), db: AsyncSession = Depends(get_db)
):
    org_id = ctx.require_organization_id()
    transfer = await reject_transfer(db, organization_id=org_id, transfer_id=transfer_id, actor_id=ctx.user_id, reason=payload.reason)
    await db.commit()
    return transfer
