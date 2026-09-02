import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import UnauthorizedError, ValidationAppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import RefreshToken, Role, User, WorkerStatus

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    result = await db.execute(
        select(User)
        .where(User.email == email.lower())
        .options(selectinload(User.role).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()

    # Constant-shape error regardless of "user not found" vs "wrong password"
    # so the response can't be used to enumerate valid emails.
    generic_error = UnauthorizedError("Incorrect email or password")

    if user is None:
        raise generic_error

    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        raise UnauthorizedError(
            f"Account temporarily locked due to repeated failed attempts. Try again after {user.locked_until.isoformat()}.",
            code="ACCOUNT_LOCKED",
        )

    # INVITED accounts may log in exactly once with their temporary password
    # (that first login is what triggers the forced password-change flow).
    # SUSPENDED / DISABLED accounts may never log in.
    if user.status not in (WorkerStatus.ACTIVE, WorkerStatus.INVITED):
        raise UnauthorizedError("Account is not active", code="ACCOUNT_INACTIVE")

    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = now + LOCKOUT_DURATION
            user.failed_login_attempts = 0
        # Commit (not just flush): this function is about to raise, and the
        # request-scoped session rolls back on exception — without an
        # explicit commit here, the lockout bookkeeping we just did would be
        # discarded along with the failed request, silently disabling the
        # lockout entirely.
        await db.commit()
        raise generic_error

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    if user.status == WorkerStatus.INVITED:
        user.status = WorkerStatus.ACTIVE
    await db.flush()
    return user


async def issue_tokens(db: AsyncSession, *, user: User) -> tuple[str, str, datetime]:
    """Returns (access_token, refresh_token, refresh_expires_at)."""
    access_token = create_access_token(user.id, extra_claims={"org": str(user.organization_id) if user.organization_id else None})
    refresh_token, jti, expires_at = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            expires_at=expires_at,
            revoked=False,
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return access_token, refresh_token, expires_at


async def rotate_refresh_token(db: AsyncSession, *, refresh_token: str) -> tuple[str, str, User]:
    """Validates + revokes the presented refresh token and issues a new pair
    (rotation limits the damage window if a refresh token is ever stolen)."""
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid or expired refresh token")

    jti = payload.get("jti")
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    stored = result.scalar_one_or_none()
    if stored is None or stored.revoked or stored.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("Refresh token is no longer valid")

    user = await db.get(User, stored.user_id)
    if user is None or user.status != WorkerStatus.ACTIVE:
        raise UnauthorizedError("Account is not active")

    stored.revoked = True
    access_token, new_refresh_token, _ = await issue_tokens(db, user=user)
    return access_token, new_refresh_token, user


async def revoke_refresh_token(db: AsyncSession, *, refresh_token: str) -> None:
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        return
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == payload.get("jti")))
    stored = result.scalar_one_or_none()
    if stored is not None:
        stored.revoked = True
        await db.flush()


async def change_password(db: AsyncSession, *, user: User, current_password: str | None, new_password: str) -> None:
    if not user.must_change_password:
        # Normal (not forced) password change requires proving the current one.
        if not current_password or not verify_password(current_password, user.hashed_password):
            raise ValidationAppError("Current password is incorrect", code="INVALID_CURRENT_PASSWORD")

    if len(new_password) < 8:
        raise ValidationAppError("New password must be at least 8 characters", code="WEAK_PASSWORD")

    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    await db.flush()

    # Revoking all outstanding refresh tokens forces re-login everywhere else.
    await db.execute(
        RefreshToken.__table__.update().where(RefreshToken.user_id == user.id).values(revoked=True)
    )
