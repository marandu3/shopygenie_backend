import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import generate_temporary_password, hash_password
from app.models.organization import Organization, SubscriptionStatus
from app.models.sale import Sale, SaleStatus
from app.models.user import Role, User, WorkerStatus
from app.schemas.platform import OrganizationProvision, PlatformKPIs
from app.services.audit import log_action


async def provision_organization(
    db: AsyncSession, *, payload: OrganizationProvision, provisioned_by: uuid.UUID
) -> tuple[Organization, User, str]:
    existing_slug = await db.execute(select(Organization).where(Organization.slug == payload.slug))
    if existing_slug.scalar_one_or_none() is not None:
        raise ConflictError("An organization with this slug already exists")

    existing_email = await db.execute(select(User).where(User.email == payload.owner_email.lower()))
    if existing_email.scalar_one_or_none() is not None:
        raise ConflictError("A user with this email already exists")

    owner_role_result = await db.execute(
        select(Role).where(Role.organization_id.is_(None), Role.name == "Tenant Owner")
    )
    owner_role = owner_role_result.scalar_one_or_none()
    if owner_role is None:
        raise NotFoundError("System role 'Tenant Owner' is not seeded — run the seed script")

    org = Organization(
        name=payload.organization_name,
        slug=payload.slug,
        currency=payload.currency,
        subscription_status=SubscriptionStatus.TRIAL,
    )
    db.add(org)
    await db.flush()

    temporary_password = generate_temporary_password()
    owner = User(
        organization_id=org.id,
        role_id=owner_role.id,
        full_name=payload.owner_full_name,
        email=payload.owner_email.lower(),
        phone=payload.owner_phone,
        hashed_password=hash_password(temporary_password),
        status=WorkerStatus.INVITED,
        must_change_password=True,
    )
    db.add(owner)
    await db.flush()

    await log_action(
        db,
        actor_user_id=provisioned_by,
        organization_id=org.id,
        action="ORGANIZATION_PROVISIONED",
        resource_type="organization",
        resource_id=str(org.id),
        acting_as_platform_owner=True,
        metadata={"owner_email": owner.email},
    )

    return org, owner, temporary_password


async def set_organization_active(
    db: AsyncSession, *, organization_id: uuid.UUID, is_active: bool, actor_id: uuid.UUID
) -> Organization:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    org.is_active = is_active
    org.subscription_status = SubscriptionStatus.SUSPENDED if not is_active else SubscriptionStatus.ACTIVE

    if not is_active:
        # Revoke every live session in this tenant immediately.
        from app.models.user import RefreshToken

        result = await db.execute(select(User.id).where(User.organization_id == organization_id))
        user_ids = [r[0] for r in result.all()]
        if user_ids:
            await db.execute(
                RefreshToken.__table__.update().where(RefreshToken.user_id.in_(user_ids)).values(revoked=True)
            )

    await log_action(
        db,
        actor_user_id=actor_id,
        organization_id=organization_id,
        action="ORGANIZATION_SUSPENDED" if not is_active else "ORGANIZATION_REACTIVATED",
        resource_type="organization",
        resource_id=str(organization_id),
        acting_as_platform_owner=True,
    )

    await db.flush()
    return org


async def platform_kpis(db: AsyncSession) -> PlatformKPIs:
    total = (await db.execute(select(func.count(Organization.id)))).scalar_one()
    active = (await db.execute(select(func.count(Organization.id)).where(Organization.is_active.is_(True)))).scalar_one()
    workers = (await db.execute(select(func.count(User.id)).where(User.is_platform_owner.is_(False)))).scalar_one()
    total_sales = (
        await db.execute(select(func.coalesce(func.sum(Sale.total_amount), 0)).where(Sale.status == SaleStatus.COMPLETED))
    ).scalar_one()

    return PlatformKPIs(
        total_organizations=total,
        active_organizations=active,
        suspended_organizations=total - active,
        total_workers=workers,
        total_sales_all_time=float(total_sales),
        generated_at=datetime.now(timezone.utc),
    )
