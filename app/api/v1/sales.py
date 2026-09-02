import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthContext, PaginationParams, require_permission
from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.permissions import SALES_CREATE, SALES_REFUND, SALES_VIEW, SALES_VOID
from app.db.session import get_db
from app.models.billing import SmsMessageType
from app.models.customer import Customer
from app.models.organization import Organization
from app.models.sale import Sale
from app.schemas.common import Page
from app.schemas.returns import SaleReturnCreate, SaleReturnOut
from app.schemas.sale import SaleCreate, SaleOut, VoidSaleRequest
from app.schemas.sms import SendSaleNotificationRequest, SmsMessageOut
from app.services.notifications import send_sms, send_whatsapp
from app.services.sale_returns import create_sale_return
from app.services.sales import build_receipt_sms, create_sale, void_sale

router = APIRouter(prefix="/sales", tags=["Sales"])


@router.post("", response_model=SaleOut, status_code=201)
async def create_sale_endpoint(
    payload: SaleCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_permission(SALES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    sale = await create_sale(db, organization_id=org_id, cashier_id=ctx.user_id, payload=payload, request=request)
    await db.commit()
    await db.refresh(sale, attribute_names=["items", "payments"])

    if payload.notify_customer and payload.customer_id is not None:
        customer = await db.get(Customer, payload.customer_id)
        org = await db.get(Organization, org_id)
        if customer is not None and customer.phone:
            message = build_receipt_sms(
                business_name=org.name,
                customer_name=customer.name,
                sale_number=sale.sale_number,
                total_amount=sale.total_amount,
                currency=org.currency,
            )
            background_tasks.add_task(
                send_sms,
                organization_id=org_id,
                to=customer.phone,
                message=message,
                message_type=SmsMessageType.SALE_RECEIPT,
                related_sale_id=sale.id,
                sent_by=ctx.user_id,
            )

    return sale


@router.post("/{sale_id}/notify", response_model=SmsMessageOut)
async def notify_sale_endpoint(
    sale_id: uuid.UUID,
    payload: SendSaleNotificationRequest,
    ctx: AuthContext = Depends(require_permission(SALES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Send/resend the receipt notification from Sale Details (MASTER PROMPT
    §45 "Later sending"). Runs inline so the caller sees the real outcome."""
    org_id = ctx.require_organization_id()
    sale = await db.get(Sale, sale_id)
    if sale is None or sale.organization_id != org_id:
        raise NotFoundError("Sale not found")
    if sale.customer_id is None:
        raise ValidationAppError("This sale has no customer to notify", code="NO_CUSTOMER")

    customer = await db.get(Customer, sale.customer_id)
    org = await db.get(Organization, org_id)
    if customer is None or not customer.phone:
        raise ValidationAppError("Customer has no phone number on file", code="NO_PHONE")

    message = build_receipt_sms(
        business_name=org.name,
        customer_name=customer.name,
        sale_number=sale.sale_number,
        total_amount=sale.total_amount,
        currency=org.currency,
    )

    if payload.channel == "whatsapp":
        await send_whatsapp(organization_id=org_id, to=customer.phone, message=message)
        return SmsMessageOut(
            id=uuid.uuid4(),
            message_type="SALE_RECEIPT",
            recipient=customer.phone,
            body=message,
            status="SENT",
            provider_message_id=None,
            error=None,
            related_sale_id=sale.id,
            created_at=datetime.now(timezone.utc),
        )

    log = await send_sms(
        organization_id=org_id,
        to=customer.phone,
        message=message,
        message_type=SmsMessageType.SALE_RECEIPT,
        related_sale_id=sale.id,
        sent_by=ctx.user_id,
    )
    return log


@router.post("/{sale_id}/returns", response_model=SaleReturnOut, status_code=201)
async def create_sale_return_endpoint(
    sale_id: uuid.UUID,
    payload: SaleReturnCreate,
    request: Request,
    ctx: AuthContext = Depends(require_permission(SALES_REFUND)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    sale_return = await create_sale_return(
        db, organization_id=org_id, sale_id=sale_id, payload=payload, processed_by=ctx.user_id, request=request
    )
    await db.commit()
    await db.refresh(sale_return, attribute_names=["items"])
    return sale_return


@router.get("", response_model=Page[SaleOut])
async def list_sales(
    ctx: AuthContext = Depends(require_permission(SALES_VIEW)),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    org_id = ctx.require_organization_id()
    total = (await db.execute(select(func.count()).select_from(Sale).where(Sale.organization_id == org_id))).scalar_one()
    result = await db.execute(
        select(Sale)
        .where(Sale.organization_id == org_id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
        .order_by(Sale.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return Page(items=list(result.scalars()), total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{sale_id}", response_model=SaleOut)
async def get_sale(
    sale_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(SALES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Sale)
        .where(Sale.id == sale_id, Sale.organization_id == org_id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
    )
    sale = result.scalar_one_or_none()
    if sale is None:
        raise NotFoundError("Sale not found")
    return sale


@router.post("/{sale_id}/void", response_model=SaleOut)
async def void_sale_endpoint(
    sale_id: uuid.UUID,
    payload: VoidSaleRequest,
    request: Request,
    ctx: AuthContext = Depends(require_permission(SALES_VOID)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    sale = await void_sale(
        db, organization_id=org_id, sale_id=sale_id, voided_by=ctx.user_id, reason=payload.reason, request=request
    )
    await db.commit()
    await db.refresh(sale, attribute_names=["items", "payments"])
    return sale
