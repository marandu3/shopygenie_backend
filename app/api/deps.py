import uuid

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import Role, RolePermission, User, WorkerStatus

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


class AuthContext:
    """Everything downstream code needs about "who is calling, from where".

    organization_id here is the ONLY organization scope any query may use.
    It is derived from the authenticated user's row in the database — never
    from a header, query param, or request body supplied by the client.
    """

    def __init__(self, user: User, permissions: set[str], acting_organization_id: uuid.UUID | None = None):
        self.user = user
        self.permissions = permissions
        # Set only when a platform owner has explicitly switched into tenant
        # mode for one organization (see /platform/organizations/{id}/enter).
        # This is never derived from anything client-supplied per request —
        # it is baked into the signed access token at switch time.
        self.acting_organization_id = acting_organization_id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def organization_id(self) -> uuid.UUID | None:
        return self.acting_organization_id or self.user.organization_id

    @property
    def is_platform_owner(self) -> bool:
        return self.user.is_platform_owner

    @property
    def is_platform_owner_acting_as_tenant(self) -> bool:
        return self.user.is_platform_owner and self.acting_organization_id is not None

    def require_organization_id(self) -> uuid.UUID:
        if self.organization_id is None:
            raise ForbiddenError("This action requires an active tenant context")
        return self.organization_id

    def has_permission(self, code: str) -> bool:
        # A platform owner acting inside a tenant has full access to that
        # tenant (and every action is audited — see services/audit.py) but is
        # not a substitute for that tenant's own permission system elsewhere.
        return self.is_platform_owner or code in self.permissions


async def get_current_context(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if not token:
        raise UnauthorizedError("Missing authentication token")

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedError("Invalid token payload")

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.role)
            .selectinload(Role.permissions)
            .selectinload(RolePermission.permission)
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise UnauthorizedError("User no longer exists")
    if user.status != WorkerStatus.ACTIVE:
        raise UnauthorizedError("Account is not active")

    permissions: set[str] = set()
    if user.role is not None:
        permissions = {rp.permission.code for rp in user.role.permissions}

    acting_organization_id: uuid.UUID | None = None
    act_org_claim = payload.get("act_org")
    if act_org_claim:
        if not user.is_platform_owner:
            raise ForbiddenError("Invalid token: tenant-mode claim on a non-platform-owner account")
        acting_organization_id = uuid.UUID(act_org_claim)

    request.state.user_id = str(user.id)
    request.state.organization_id = str(acting_organization_id or user.organization_id or "")

    return AuthContext(user=user, permissions=permissions, acting_organization_id=acting_organization_id)


async def require_password_already_set(ctx: AuthContext = Depends(get_current_context)) -> AuthContext:
    """Blocks access to the main application until a forced password change
    is complete. Only the auth/change-password endpoints skip this check."""
    if ctx.user.must_change_password:
        raise ForbiddenError(
            "Password change required before continuing", code="PASSWORD_CHANGE_REQUIRED"
        )
    return ctx


def require_permission(permission_code: str):
    async def _checker(ctx: AuthContext = Depends(require_password_already_set)) -> AuthContext:
        if not ctx.has_permission(permission_code):
            raise ForbiddenError(f"Missing required permission: {permission_code}")
        return ctx

    return _checker


async def require_platform_owner(ctx: AuthContext = Depends(require_password_already_set)) -> AuthContext:
    if not ctx.is_platform_owner:
        raise ForbiddenError("This action is restricted to the platform owner")
    return ctx


async def require_tenant_context(ctx: AuthContext = Depends(require_password_already_set)) -> AuthContext:
    """Use on every tenant-scoped route: guarantees ctx.organization_id is set."""
    ctx.require_organization_id()
    return ctx
