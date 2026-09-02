from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.account_request import TenantAccountRequestCreate, TenantAccountRequestOut
from app.services.account_requests import submit_account_request

router = APIRouter(prefix="/account-requests", tags=["Account Requests"])


@router.post("", response_model=TenantAccountRequestOut, status_code=201)
async def submit_account_request_endpoint(payload: TenantAccountRequestCreate, db: AsyncSession = Depends(get_db)):
    """Public — no authentication. A prospective tenant asks for an account;
    a platform owner reviews and approves/rejects it (see /platform/account-requests)."""
    request = await submit_account_request(db, payload=payload)
    await db.commit()
    return request
