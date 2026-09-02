import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.account_request import AccountRequestStatus, TenantAccountRequest
from app.models.notification import NotificationType
from app.models.organization import Organization
from app.models.user import User
from app.schemas.account_request import AccountRequestApprove, TenantAccountRequestCreate
from app.schemas.platform import OrganizationProvision
from app.services.audit import log_action
from app.services.notification_center import create_notification
from app.services.platform import provision_organization


async def submit_account_request(db: AsyncSession, *, payload: TenantAccountRequestCreate) -> TenantAccountRequest:
    request = TenantAccountRequest(
        organization_name=payload.organization_name,
        applicant_name=payload.applicant_name,
        email=payload.email.lower(),
        phone=payload.phone,
        business_type=payload.business_type,
        location=payload.location,
        expected_usage=payload.expected_usage,
        additional_info=payload.additional_info,
        status=AccountRequestStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    db.add(request)
    await db.flush()

    await create_notification(
        db,
        organization_id=None,
        type=NotificationType.ACTION_REQUIRED,
        title="New tenant account request",
        body=f"{payload.applicant_name} requested an account for '{payload.organization_name}'.",
        link="/platform",
        resource_type="tenant_account_request",
        resource_id=str(request.id),
    )
    return request


async def set_under_review(db: AsyncSession, *, request_id: uuid.UUID, actor_id: uuid.UUID, note: str | None) -> TenantAccountRequest:
    request = await db.get(TenantAccountRequest, request_id)
    if request is None:
        raise NotFoundError("Account request not found")
    if request.status != AccountRequestStatus.PENDING:
        raise ValidationAppError("Only a pending request can be moved to review", code="INVALID_REQUEST_STATUS")
    request.status = AccountRequestStatus.UNDER_REVIEW
    request.review_note = note
    request.reviewed_by = actor_id
    request.reviewed_at = datetime.now(timezone.utc)
    await log_action(db, actor_user_id=actor_id, organization_id=None, action="ACCOUNT_REQUEST_UNDER_REVIEW", resource_type="tenant_account_request", resource_id=str(request.id), acting_as_platform_owner=True)
    await db.flush()
    return request


async def reject_account_request(db: AsyncSession, *, request_id: uuid.UUID, actor_id: uuid.UUID, note: str) -> TenantAccountRequest:
    request = await db.get(TenantAccountRequest, request_id)
    if request is None:
        raise NotFoundError("Account request not found")
    if request.status in (AccountRequestStatus.APPROVED, AccountRequestStatus.REJECTED):
        raise ValidationAppError("This request has already been finalized", code="INVALID_REQUEST_STATUS")
    request.status = AccountRequestStatus.REJECTED
    request.review_note = note
    request.reviewed_by = actor_id
    request.reviewed_at = datetime.now(timezone.utc)
    await log_action(db, actor_user_id=actor_id, organization_id=None, action="ACCOUNT_REQUEST_REJECTED", resource_type="tenant_account_request", resource_id=str(request.id), reason=note, acting_as_platform_owner=True)
    await db.flush()
    return request


async def approve_account_request(
    db: AsyncSession, *, request_id: uuid.UUID, actor_id: uuid.UUID, payload: AccountRequestApprove
) -> tuple[TenantAccountRequest, Organization, User, str]:
    request = await db.get(TenantAccountRequest, request_id)
    if request is None:
        raise NotFoundError("Account request not found")
    if request.status in (AccountRequestStatus.APPROVED, AccountRequestStatus.REJECTED):
        raise ValidationAppError("This request has already been finalized", code="INVALID_REQUEST_STATUS")

    provision_payload = OrganizationProvision(
        organization_name=request.organization_name,
        slug=payload.slug,
        owner_full_name=request.applicant_name,
        owner_email=request.email,
        owner_phone=request.phone,
        currency=payload.currency,
    )
    org, owner, temporary_password = await provision_organization(db, payload=provision_payload, provisioned_by=actor_id)

    request.status = AccountRequestStatus.APPROVED
    request.reviewed_by = actor_id
    request.reviewed_at = datetime.now(timezone.utc)
    request.organization_id = org.id

    await log_action(db, actor_user_id=actor_id, organization_id=org.id, action="ACCOUNT_REQUEST_APPROVED", resource_type="tenant_account_request", resource_id=str(request.id), acting_as_platform_owner=True)
    await db.flush()
    return request, org, owner, temporary_password
