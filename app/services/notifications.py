import uuid
from datetime import datetime, timezone

from app.db.session import get_session_factory
from app.integrations.sms import get_sms_provider
from app.integrations.whatsapp import get_whatsapp_provider
from app.models.billing import SmsMessage, SmsMessageStatus, SmsMessageType
from app.models.organization import Organization
from app.services.usage import SMS_METRIC, WHATSAPP_METRIC, enforce_whatsapp_quota, increment_usage


async def send_sms(
    *,
    organization_id: uuid.UUID,
    to: str,
    message: str,
    message_type: SmsMessageType = SmsMessageType.TEST,
    related_sale_id: uuid.UUID | None = None,
    sent_by: uuid.UUID | None = None,
) -> SmsMessage:
    """Single chokepoint every SMS-triggering flow calls through (MASTER
    PROMPT §39, §78). Opens its own session — this runs as a FastAPI
    BackgroundTask after the request's own session has already closed.
    Always writes exactly one SmsMessage row (MASTER PROMPT §45 message
    history), success or failure."""
    async with get_session_factory()() as db:
        organization = await db.get(Organization, organization_id)
        if organization is None:
            raise ValueError(f"Organization {organization_id} not found")

        provider = get_sms_provider(organization)
        result = await provider.send(to=to, message=message)

        log = SmsMessage(
            organization_id=organization_id,
            message_type=message_type,
            recipient=to,
            body=message,
            status=SmsMessageStatus.SENT if result.success else SmsMessageStatus.FAILED,
            provider_message_id=result.provider_message_id,
            error=result.error,
            related_sale_id=related_sale_id,
            sent_by=sent_by,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)

        # SMS/email stay unlimited while active but are still counted for
        # transparency (MASTER PROMPT §63).
        await increment_usage(db, organization_id=organization_id, metric=SMS_METRIC)

        await db.commit()
        await db.refresh(log)
        return log


async def send_whatsapp(*, organization_id: uuid.UUID, to: str, message: str) -> None:
    """WhatsApp is metered per MASTER PROMPT §63 — hard-blocked once the
    plan's monthly quota is exhausted (§66), never silently dropped. See
    app/integrations/whatsapp for why this sends through a console stub."""
    async with get_session_factory()() as db:
        organization = await db.get(Organization, organization_id)
        if organization is None:
            raise ValueError(f"Organization {organization_id} not found")

        await enforce_whatsapp_quota(db, organization)

        provider = get_whatsapp_provider()
        await provider.send(to=to, message=message)

        await increment_usage(db, organization_id=organization_id, metric=WHATSAPP_METRIC)
        await db.commit()
