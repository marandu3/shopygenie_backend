from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_context
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.db.session import get_db
from app.schemas.auth import ChangePasswordRequest, CurrentUser, LoginRequest, TokenResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])

REFRESH_COOKIE_NAME = "shopygenie_refresh_token"


def _to_current_user(ctx: AuthContext) -> CurrentUser:
    return CurrentUser(
        id=ctx.user.id,
        organization_id=ctx.organization_id,
        full_name=ctx.user.full_name,
        email=ctx.user.email,
        is_platform_owner=ctx.user.is_platform_owner,
        acting_as_platform_owner=ctx.is_platform_owner_acting_as_tenant,
        must_change_password=ctx.user.must_change_password,
        role_name=ctx.user.role.name if ctx.user.role else None,
        permissions=sorted(ctx.permissions),
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path="/api/v1/auth",
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate(db, email=payload.email, password=payload.password)
    access_token, refresh_token, _ = await auth_service.issue_tokens(db, user=user)
    await db.commit()

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token, must_change_password=user.must_change_password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    shopygenie_refresh_token: str | None = Cookie(default=None),
):
    if not shopygenie_refresh_token:
        raise UnauthorizedError("Missing refresh token")

    access_token, new_refresh_token, user = await auth_service.rotate_refresh_token(
        db, refresh_token=shopygenie_refresh_token
    )
    await db.commit()

    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=access_token, must_change_password=user.must_change_password)


@router.post("/logout")
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    shopygenie_refresh_token: str | None = Cookie(default=None),
):
    if shopygenie_refresh_token:
        await auth_service.revoke_refresh_token(db, refresh_token=shopygenie_refresh_token)
        await db.commit()
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return {"detail": "Logged out"}


@router.post("/change-password", response_model=CurrentUser)
async def change_password(
    payload: ChangePasswordRequest,
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.change_password(
        db, user=ctx.user, current_password=payload.current_password, new_password=payload.new_password
    )
    await db.commit()
    return _to_current_user(ctx)


@router.get("/me", response_model=CurrentUser)
async def me(request: Request, ctx: AuthContext = Depends(get_current_context)):
    return _to_current_user(ctx)
