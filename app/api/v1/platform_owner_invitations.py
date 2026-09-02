import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_platform_owner
from app.db.session import get_db
from app.schemas.common import MessageResponse
from app.schemas.platform_owner_invitation import (
    PlatformOwnerInvitationAccept,
    PlatformOwnerInvitationCreate,
    PlatformOwnerInvitationCreated,
    PlatformOwnerInvitationOut,
)
from app.services.platform_owner_invitations import (
    accept_invitation,
    create_invitation,
    list_invitations,
    revoke_invitation,
)

router = APIRouter(prefix="/platform/owner-invitations", tags=["Platform Owner Invitations"])


@router.post("", response_model=PlatformOwnerInvitationCreated, status_code=201)
async def create_invitation_endpoint(
    payload: PlatformOwnerInvitationCreate,
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    invitation, token = await create_invitation(db, invited_by=ctx.user_id, payload=payload)
    await db.commit()
    await db.refresh(invitation)
    return PlatformOwnerInvitationCreated(
        id=invitation.id,
        email=invitation.email,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        token=token,
    )


@router.get("", response_model=list[PlatformOwnerInvitationOut])
async def list_invitations_endpoint(ctx: AuthContext = Depends(require_platform_owner), db: AsyncSession = Depends(get_db)):
    return await list_invitations(db)


@router.post("/{invitation_id}/revoke", response_model=PlatformOwnerInvitationOut)
async def revoke_invitation_endpoint(
    invitation_id: uuid.UUID, ctx: AuthContext = Depends(require_platform_owner), db: AsyncSession = Depends(get_db)
):
    invitation = await revoke_invitation(db, invitation_id=invitation_id, actor_id=ctx.user_id)
    await db.commit()
    return invitation


@router.post("/accept", response_model=MessageResponse)
async def accept_invitation_endpoint(payload: PlatformOwnerInvitationAccept, db: AsyncSession = Depends(get_db)):
    """Public — no authentication. The invitee sets their own password here;
    afterwards they log in normally through /auth/login."""
    user = await accept_invitation(db, payload=payload)
    await db.commit()
    return MessageResponse(detail=f"Account created for {user.email}. You can now log in.")
