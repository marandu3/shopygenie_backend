import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.security import generate_temporary_password, hash_password
from app.models.notification import NotificationType
from app.models.organization import Organization
from app.models.user import Permission, Role, RolePermission, User, WorkerStatus
from app.schemas.user import RoleCreate, RoleUpdate, WorkerInvite
from app.services.audit import log_action
from app.services.notification_center import create_notification


async def invite_worker(
    db: AsyncSession, *, organization_id: uuid.UUID, invited_by: uuid.UUID, payload: WorkerInvite
) -> tuple[User, str]:
    """Creates the worker with a temporary password and returns it so the
    caller can send it via SMS (MASTER PROMPT §9-10). The plaintext password
    is NEVER stored — only its bcrypt hash — and is not returned to the
    frontend in the API response, only handed back here for one-time SMS use.
    """
    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("A user with this email already exists")

    role = await db.get(Role, payload.role_id)
    if role is None or (role.organization_id is not None and role.organization_id != organization_id):
        raise ValidationAppError("Invalid role for this organization", code="INVALID_ROLE")

    org = await db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    temporary_password = generate_temporary_password()

    worker = User(
        organization_id=organization_id,
        branch_id=payload.branch_id,
        register_id=payload.register_id,
        role_id=payload.role_id,
        full_name=payload.full_name,
        email=payload.email.lower(),
        phone=payload.phone,
        hashed_password=hash_password(temporary_password),
        status=WorkerStatus.INVITED,
        must_change_password=True,
    )
    db.add(worker)
    await db.flush()

    await log_action(
        db,
        actor_user_id=invited_by,
        organization_id=organization_id,
        action="WORKER_INVITED",
        resource_type="user",
        resource_id=str(worker.id),
        metadata={"email": worker.email, "role_id": str(payload.role_id)},
    )

    await create_notification(
        db,
        organization_id=organization_id,
        type=NotificationType.INFO,
        title="New worker invited",
        body=f"{worker.full_name} was invited as a new worker.",
        link="/workers",
        resource_type="user",
        resource_id=str(worker.id),
    )

    return worker, temporary_password


def build_invitation_sms(*, business_name: str, worker_name: str, email: str, temporary_password: str) -> str:
    return (
        f"{business_name}: Hi {worker_name}, your ShopyGenie account is ready.\n"
        f"Login: {email}\nTemporary password: {temporary_password}\n"
        f"You'll be asked to set a new password on first login."
    )


async def set_worker_status(
    db: AsyncSession, *, organization_id: uuid.UUID, worker_id: uuid.UUID, status: WorkerStatus, actor_id: uuid.UUID
) -> User:
    worker = await db.get(User, worker_id)
    if worker is None or worker.organization_id != organization_id:
        raise NotFoundError("Worker not found")

    worker.status = status
    if status == WorkerStatus.SUSPENDED:
        # Immediately invalidate any live sessions.
        from app.models.user import RefreshToken

        await db.execute(RefreshToken.__table__.update().where(RefreshToken.user_id == worker.id).values(revoked=True))

    await log_action(
        db,
        actor_user_id=actor_id,
        organization_id=organization_id,
        action=f"WORKER_{status.value}",
        resource_type="user",
        resource_id=str(worker.id),
    )
    await db.flush()
    return worker


async def _resolve_permissions(db: AsyncSession, codes: list[str]) -> list[Permission]:
    if not codes:
        return []
    result = await db.execute(select(Permission).where(Permission.code.in_(codes)))
    found = list(result.scalars())
    found_codes = {p.code for p in found}
    unknown = set(codes) - found_codes
    if unknown:
        raise ValidationAppError(f"Unknown permission code(s): {', '.join(sorted(unknown))}", code="INVALID_PERMISSION")
    return found


async def create_custom_role(db: AsyncSession, *, organization_id: uuid.UUID, actor_id: uuid.UUID, payload: RoleCreate) -> Role:
    """Tenant Owners can define their own roles beyond the built-in system
    set (MASTER PROMPT §42). Authorization is still enforced purely by the
    permission codes attached here — a custom role name carries no special
    meaning to the backend."""
    permissions = await _resolve_permissions(db, payload.permissions)

    role = Role(organization_id=organization_id, name=payload.name, is_system=False)
    db.add(role)
    await db.flush()
    for perm in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    await log_action(
        db,
        actor_user_id=actor_id,
        organization_id=organization_id,
        action="ROLE_CREATED",
        resource_type="role",
        resource_id=str(role.id),
        metadata={"name": role.name, "permissions": payload.permissions},
    )
    await db.flush()

    result = await db.execute(
        select(Role).where(Role.id == role.id).options(selectinload(Role.permissions).selectinload(RolePermission.permission))
    )
    return result.scalar_one()


async def update_custom_role(
    db: AsyncSession, *, organization_id: uuid.UUID, role_id: uuid.UUID, actor_id: uuid.UUID, payload: RoleUpdate
) -> Role:
    role = await db.get(Role, role_id)
    if role is None or role.organization_id != organization_id:
        raise NotFoundError("Role not found")
    if role.is_system:
        raise ValidationAppError("System roles cannot be edited", code="SYSTEM_ROLE_READONLY")

    if payload.name is not None:
        role.name = payload.name

    if payload.permissions is not None:
        permissions = await _resolve_permissions(db, payload.permissions)
        await db.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role.id))
        await db.flush()
        for perm in permissions:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    await log_action(
        db,
        actor_user_id=actor_id,
        organization_id=organization_id,
        action="ROLE_UPDATED",
        resource_type="role",
        resource_id=str(role.id),
    )
    await db.flush()

    result = await db.execute(
        select(Role).where(Role.id == role.id).options(selectinload(Role.permissions).selectinload(RolePermission.permission))
    )
    return result.scalar_one()


async def delete_custom_role(db: AsyncSession, *, organization_id: uuid.UUID, role_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    role = await db.get(Role, role_id)
    if role is None or role.organization_id != organization_id:
        raise NotFoundError("Role not found")
    if role.is_system:
        raise ValidationAppError("System roles cannot be deleted", code="SYSTEM_ROLE_READONLY")

    in_use = await db.execute(select(User.id).where(User.role_id == role_id).limit(1))
    if in_use.scalar_one_or_none() is not None:
        raise ValidationAppError("This role is still assigned to at least one worker", code="ROLE_IN_USE")

    await log_action(
        db,
        actor_user_id=actor_id,
        organization_id=organization_id,
        action="ROLE_DELETED",
        resource_type="role",
        resource_id=str(role.id),
        metadata={"name": role.name},
    )
    await db.delete(role)
    await db.flush()
