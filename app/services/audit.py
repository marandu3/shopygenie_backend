import uuid
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
    acting_as_platform_owner: bool = False,
    request: Request | None = None,
) -> None:
    """WHO / WHAT / WHEN / WHERE / WHY / REFERENCE — see MASTER PROMPT §119.

    Call this inside the same transaction as the mutation it describes so an
    audit entry can never exist without (or diverge from) the change it logs.
    """
    entry = AuditLog(
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        acting_as_platform_owner=acting_as_platform_owner,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        reason=reason,
        metadata_json=metadata,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
