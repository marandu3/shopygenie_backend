import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.billing import ActivationRequest, ActivationRequestStatus
from app.models.organization import Organization, SubscriptionStatus
from app.schemas.billing import ActivationRequestApprove, ActivationRequestCreate, ActivationRequestReject
from app.services.audit import log_action


async def submit_activation_request(
    db: AsyncSession, *, organization_id: uuid.UUID, requested_by: uuid.UUID, payload: ActivationRequestCreate
) -> ActivationRequest:
    request = ActivationRequest(
        organization_id=organization_id,
        requested_by=requested_by,
        plan_requested=payload.plan_requested,
        reference_number=payload.reference_number.strip(),
        note=payload.note,
    )
    db.add(request)
    await db.flush()

    await log_action(
        db,
        actor_user_id=requested_by,
        organization_id=organization_id,
        action="ACTIVATION_REQUEST_SUBMITTED",
        resource_type="activation_request",
        resource_id=str(request.id),
        metadata={"plan_requested": payload.plan_requested.value, "reference_number": request.reference_number},
    )
    return request


async def approve_activation_request(
    db: AsyncSession, *, request_id: uuid.UUID, actor_id: uuid.UUID, payload: ActivationRequestApprove
) -> ActivationRequest:
    request = await db.get(ActivationRequest, request_id)
    if request is None:
        raise NotFoundError("Activation request not found")
    if request.status != ActivationRequestStatus.PENDING:
        raise ConflictError("This activation request has already been reviewed")

    org = await db.get(Organization, request.organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    now = datetime.now(timezone.utc)
    request.status = ActivationRequestStatus.APPROVED
    request.reviewed_by = actor_id
    request.reviewed_at = now
    request.review_note = payload.review_note

    org.subscription_status = SubscriptionStatus.ACTIVE
    org.subscription_plan = request.plan_requested
    org.subscription_expires_at = now + timedelta(days=payload.duration_days)
    org.is_active = True

    await log_action(
        db,
        actor_user_id=actor_id,
        organization_id=request.organization_id,
        action="ACTIVATION_REQUEST_APPROVED",
        resource_type="activation_request",
        resource_id=str(request.id),
        acting_as_platform_owner=True,
        metadata={
            "plan_requested": request.plan_requested.value,
            "duration_days": payload.duration_days,
            "expires_at": org.subscription_expires_at.isoformat(),
        },
    )
    await db.flush()
    return request


async def reject_activation_request(
    db: AsyncSession, *, request_id: uuid.UUID, actor_id: uuid.UUID, payload: ActivationRequestReject
) -> ActivationRequest:
    request = await db.get(ActivationRequest, request_id)
    if request is None:
        raise NotFoundError("Activation request not found")
    if request.status != ActivationRequestStatus.PENDING:
        raise ConflictError("This activation request has already been reviewed")

    request.status = ActivationRequestStatus.REJECTED
    request.reviewed_by = actor_id
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = payload.review_note

    await log_action(
        db,
        actor_user_id=actor_id,
        organization_id=request.organization_id,
        action="ACTIVATION_REQUEST_REJECTED",
        resource_type="activation_request",
        resource_id=str(request.id),
        acting_as_platform_owner=True,
        reason=payload.review_note,
    )
    await db.flush()
    return request


async def platform_list_activation_requests(
    db: AsyncSession, *, status_filter: ActivationRequestStatus | None, offset: int, limit: int
) -> tuple[list[tuple[ActivationRequest, str]], int]:
    conditions = [ActivationRequest.status == status_filter] if status_filter else []

    total = (
        await db.execute(select(func.count()).select_from(ActivationRequest).where(*conditions))
    ).scalar_one()

    result = await db.execute(
        select(ActivationRequest, Organization.name)
        .join(Organization, Organization.id == ActivationRequest.organization_id)
        .where(*conditions)
        .order_by(ActivationRequest.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.all()), total
