import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.security import generate_secure_token, hash_password, hash_token
from app.models.organization import Organization
from app.models.platform_owner_invitation import PlatformOwnerInvitation, PlatformOwnerInvitationStatus
from app.models.user import User, WorkerStatus
from app.schemas.platform_owner_invitation import PlatformOwnerInvitationAccept, PlatformOwnerInvitationCreate
from app.services.audit import log_action

INVITATION_TTL_DAYS = 7
PLATFORM_ORG_SLUG = "shopygenie-platform"


async def get_or_create_platform_organization(db: AsyncSession) -> Organization:
    """The dedicated home organization every platform owner belongs to for
    Tenant Mode (MASTER PROMPT §11) — idempotent, mirrors the demo-tenant
    seeding pattern in scripts/seed.py."""
    result = await db.execute(select(Organization).where(Organization.slug == PLATFORM_ORG_SLUG))
    org = result.scalar_one_or_none()
    if org is not None:
        return org
    org = Organization(name="ShopyGenie Platform", slug=PLATFORM_ORG_SLUG)
    db.add(org)
    await db.flush()
    return org


async def create_invitation(
    db: AsyncSession, *, invited_by: uuid.UUID, payload: PlatformOwnerInvitationCreate
) -> tuple[PlatformOwnerInvitation, str]:
    existing_user = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing_user.scalar_one_or_none() is not None:
        raise ConflictError("A user with this email already exists")

    token = generate_secure_token()
    invitation = PlatformOwnerInvitation(
        email=payload.email.lower(),
        token_hash=hash_token(token),
        invited_by=invited_by,
        status=PlatformOwnerInvitationStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_TTL_DAYS),
        created_at=datetime.now(timezone.utc),
    )
    db.add(invitation)
    await db.flush()

    await log_action(
        db, actor_user_id=invited_by, organization_id=None, action="PLATFORM_OWNER_INVITED",
        resource_type="platform_owner_invitation", resource_id=str(invitation.id),
        metadata={"email": invitation.email}, acting_as_platform_owner=True,
    )
    return invitation, token


async def revoke_invitation(db: AsyncSession, *, invitation_id: uuid.UUID, actor_id: uuid.UUID) -> PlatformOwnerInvitation:
    invitation = await db.get(PlatformOwnerInvitation, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found")
    if invitation.status != PlatformOwnerInvitationStatus.PENDING:
        raise ValidationAppError("Only a pending invitation can be revoked", code="INVALID_INVITATION_STATUS")
    invitation.status = PlatformOwnerInvitationStatus.REVOKED
    await log_action(db, actor_user_id=actor_id, organization_id=None, action="PLATFORM_OWNER_INVITATION_REVOKED", resource_type="platform_owner_invitation", resource_id=str(invitation.id), acting_as_platform_owner=True)
    await db.flush()
    return invitation


async def accept_invitation(db: AsyncSession, *, payload: PlatformOwnerInvitationAccept) -> User:
    result = await db.execute(
        select(PlatformOwnerInvitation).where(PlatformOwnerInvitation.token_hash == hash_token(payload.token))
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise NotFoundError("Invitation not found")
    if invitation.status != PlatformOwnerInvitationStatus.PENDING:
        raise ValidationAppError("This invitation is no longer valid", code="INVALID_INVITATION_STATUS")
    if invitation.expires_at < datetime.now(timezone.utc):
        invitation.status = PlatformOwnerInvitationStatus.EXPIRED
        await db.flush()
        raise ValidationAppError("This invitation has expired", code="INVITATION_EXPIRED")

    platform_org = await get_or_create_platform_organization(db)

    user = User(
        organization_id=platform_org.id,
        full_name=payload.full_name,
        email=invitation.email,
        hashed_password=hash_password(payload.password),
        is_platform_owner=True,
        status=WorkerStatus.ACTIVE,
        must_change_password=False,
    )
    db.add(user)

    invitation.status = PlatformOwnerInvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(timezone.utc)
    await db.flush()

    await log_action(
        db, actor_user_id=user.id, organization_id=platform_org.id, action="PLATFORM_OWNER_INVITATION_ACCEPTED",
        resource_type="user", resource_id=str(user.id), acting_as_platform_owner=True,
    )
    await db.flush()
    return user


async def list_invitations(db: AsyncSession) -> list[PlatformOwnerInvitation]:
    result = await db.execute(select(PlatformOwnerInvitation).order_by(PlatformOwnerInvitation.created_at.desc()))
    return list(result.scalars())
