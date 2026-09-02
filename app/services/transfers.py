import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.organization import Branch
from app.models.transfer import InventoryTransfer, InventoryTransferItem, TransferStatus
from app.schemas.transfer import TransferCreate
from app.services.audit import log_action


async def _load(db: AsyncSession, *, organization_id: uuid.UUID, transfer_id: uuid.UUID) -> InventoryTransfer:
    result = await db.execute(
        select(InventoryTransfer)
        .where(InventoryTransfer.id == transfer_id, InventoryTransfer.organization_id == organization_id)
        .options(selectinload(InventoryTransfer.items))
        .with_for_update()
    )
    transfer = result.scalar_one_or_none()
    if transfer is None:
        raise NotFoundError("Transfer not found")
    return transfer


async def create_transfer(
    db: AsyncSession, *, organization_id: uuid.UUID, requested_by: uuid.UUID, payload: TransferCreate
) -> InventoryTransfer:
    if payload.source_branch_id == payload.destination_branch_id:
        raise ValidationAppError("Source and destination branch must differ", code="INVALID_TRANSFER")

    for branch_id in (payload.source_branch_id, payload.destination_branch_id):
        branch = await db.get(Branch, branch_id)
        if branch is None or branch.organization_id != organization_id:
            raise NotFoundError(f"Branch {branch_id} not found")

    now = datetime.now(timezone.utc)
    transfer = InventoryTransfer(
        organization_id=organization_id,
        source_branch_id=payload.source_branch_id,
        destination_branch_id=payload.destination_branch_id,
        note=payload.note,
        status=TransferStatus.REQUESTED,
        requested_by=requested_by,
        requested_at=now,
        items=[InventoryTransferItem(product_id=i.product_id, quantity=i.quantity) for i in payload.items],
    )
    db.add(transfer)
    await db.flush()

    await log_action(
        db, actor_user_id=requested_by, organization_id=organization_id, action="TRANSFER_REQUESTED",
        resource_type="inventory_transfer", resource_id=str(transfer.id),
    )
    result = await db.execute(
        select(InventoryTransfer).where(InventoryTransfer.id == transfer.id).options(selectinload(InventoryTransfer.items))
    )
    return result.scalar_one()


async def approve_transfer(db: AsyncSession, *, organization_id: uuid.UUID, transfer_id: uuid.UUID, actor_id: uuid.UUID) -> InventoryTransfer:
    transfer = await _load(db, organization_id=organization_id, transfer_id=transfer_id)
    if transfer.status != TransferStatus.REQUESTED:
        raise ValidationAppError("Only a requested transfer can be approved", code="INVALID_TRANSFER_STATUS")
    transfer.status = TransferStatus.APPROVED
    transfer.approved_by = actor_id
    transfer.approved_at = datetime.now(timezone.utc)
    await log_action(db, actor_user_id=actor_id, organization_id=organization_id, action="TRANSFER_APPROVED", resource_type="inventory_transfer", resource_id=str(transfer.id))
    await db.flush()
    return transfer


async def mark_in_transit(db: AsyncSession, *, organization_id: uuid.UUID, transfer_id: uuid.UUID, actor_id: uuid.UUID) -> InventoryTransfer:
    transfer = await _load(db, organization_id=organization_id, transfer_id=transfer_id)
    if transfer.status != TransferStatus.APPROVED:
        raise ValidationAppError("Only an approved transfer can move to in-transit", code="INVALID_TRANSFER_STATUS")
    transfer.status = TransferStatus.IN_TRANSIT
    await log_action(db, actor_user_id=actor_id, organization_id=organization_id, action="TRANSFER_IN_TRANSIT", resource_type="inventory_transfer", resource_id=str(transfer.id))
    await db.flush()
    return transfer


async def receive_transfer(db: AsyncSession, *, organization_id: uuid.UUID, transfer_id: uuid.UUID, actor_id: uuid.UUID) -> InventoryTransfer:
    transfer = await _load(db, organization_id=organization_id, transfer_id=transfer_id)
    if transfer.status != TransferStatus.IN_TRANSIT:
        raise ValidationAppError("Only an in-transit transfer can be received", code="INVALID_TRANSFER_STATUS")
    transfer.status = TransferStatus.COMPLETED
    transfer.received_by = actor_id
    transfer.received_at = datetime.now(timezone.utc)
    await log_action(db, actor_user_id=actor_id, organization_id=organization_id, action="TRANSFER_COMPLETED", resource_type="inventory_transfer", resource_id=str(transfer.id))
    await db.flush()
    return transfer


async def reject_transfer(db: AsyncSession, *, organization_id: uuid.UUID, transfer_id: uuid.UUID, actor_id: uuid.UUID, reason: str) -> InventoryTransfer:
    transfer = await _load(db, organization_id=organization_id, transfer_id=transfer_id)
    if transfer.status in (TransferStatus.COMPLETED, TransferStatus.REJECTED):
        raise ValidationAppError("This transfer can no longer be rejected", code="INVALID_TRANSFER_STATUS")
    transfer.status = TransferStatus.REJECTED
    await log_action(db, actor_user_id=actor_id, organization_id=organization_id, action="TRANSFER_REJECTED", resource_type="inventory_transfer", resource_id=str(transfer.id), reason=reason)
    await db.flush()
    return transfer


async def list_transfers(db: AsyncSession, *, organization_id: uuid.UUID) -> list[InventoryTransfer]:
    result = await db.execute(
        select(InventoryTransfer)
        .where(InventoryTransfer.organization_id == organization_id)
        .options(selectinload(InventoryTransfer.items))
        .order_by(InventoryTransfer.requested_at.desc())
    )
    return list(result.scalars())
