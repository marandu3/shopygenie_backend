import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.exceptions import NotFoundError
from app.models.billing import SmsMessageType
from app.models.organization import Organization
from app.schemas.sms import SmsConfigOut, SmsConfigUpdate
from app.services.audit import log_action


def _to_out(org: Organization) -> SmsConfigOut:
    password = decrypt_secret(org.sms_password_encrypted) if org.sms_password_encrypted else None
    return SmsConfigOut(
        enabled=org.sms_enabled,
        base_url=org.sms_base_url,
        username=org.sms_username,
        device_id=org.sms_device_id,
        password_masked=mask_secret(password) if password else None,
        last_tested_at=org.sms_last_tested_at,
        last_test_status=org.sms_last_test_status,
        last_test_error=org.sms_last_test_error,
    )


async def update_sms_config(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_id: uuid.UUID, payload: SmsConfigUpdate
) -> SmsConfigOut:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    if payload.base_url is not None:
        org.sms_base_url = payload.base_url or None
    if payload.username is not None:
        org.sms_username = payload.username or None
    if payload.password is not None:
        # A non-empty value replaces the stored secret; the API never
        # receives the existing plaintext back to "not change" it, so an
        # empty string is used to explicitly leave it untouched — enforced
        # by min_length=1 on the schema field when supplied at all.
        org.sms_password_encrypted = encrypt_secret(payload.password)
    if payload.device_id is not None:
        org.sms_device_id = payload.device_id or None
    if payload.enabled is not None:
        org.sms_enabled = payload.enabled

    await log_action(
        db,
        actor_user_id=actor_id,
        organization_id=organization_id,
        action="SMS_CONFIG_UPDATED",
        resource_type="organization",
        resource_id=str(organization_id),
        metadata={"enabled": org.sms_enabled, "base_url": org.sms_base_url},
    )
    await db.flush()
    await db.refresh(org)
    return _to_out(org)


async def get_sms_config(db: AsyncSession, *, organization_id: uuid.UUID) -> SmsConfigOut:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return _to_out(org)


async def record_test_result(db: AsyncSession, *, organization_id: uuid.UUID, success: bool, error: str | None) -> None:
    org = await db.get(Organization, organization_id)
    if org is None:
        return
    org.sms_last_tested_at = datetime.now(timezone.utc)
    org.sms_last_test_status = "SUCCESS" if success else "FAILED"
    org.sms_last_test_error = error
    await db.flush()


TEST_MESSAGE_TYPE = SmsMessageType.TEST
