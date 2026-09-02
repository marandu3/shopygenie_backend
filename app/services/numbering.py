import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.counter import DocumentCounter


async def next_document_number(db: AsyncSession, organization_id: uuid.UUID, prefix: str) -> str:
    """Atomically issues the next number for e.g. prefix="SALE" -> "SALE-2026-000001".

    Locks the counter row for the current (org, prefix, year) so concurrent
    requests never hand out the same number.
    """
    year = datetime.now(timezone.utc).year
    key = f"{prefix}-{year}"

    result = await db.execute(
        select(DocumentCounter)
        .where(DocumentCounter.organization_id == organization_id, DocumentCounter.key == key)
        .with_for_update()
    )
    counter = result.scalar_one_or_none()

    if counter is None:
        counter = DocumentCounter(organization_id=organization_id, key=key, value=0)
        db.add(counter)
        await db.flush()
        # Re-select with lock to be safe under concurrent first-inserts.
        result = await db.execute(
            select(DocumentCounter)
            .where(DocumentCounter.organization_id == organization_id, DocumentCounter.key == key)
            .with_for_update()
        )
        counter = result.scalar_one()

    counter.value += 1
    await db.flush()

    return f"{key}-{counter.value:06d}"
