from app.core.crypto import decrypt_secret
from app.integrations.sms.base import SMSProvider
from app.integrations.sms.console_provider import ConsoleSMSProvider
from app.integrations.sms.smsgate_provider import SMSGateProvider
from app.models.organization import Organization


def get_sms_provider(organization: Organization) -> SMSProvider:
    """Tenant-scoped only (MASTER PROMPT §43: "Never use a global SMSGate
    credential for all tenants"). Falls back to a console-logging stub when
    the tenant hasn't configured/enabled SMSGate yet — never a shared
    platform-wide credential."""
    if organization.sms_enabled and organization.sms_base_url and organization.sms_api_key_encrypted:
        api_key = decrypt_secret(organization.sms_api_key_encrypted)
        if api_key:
            return SMSGateProvider(
                base_url=organization.sms_base_url,
                api_key=api_key,
                sender_id=organization.sms_sender_id or "",
            )
    return ConsoleSMSProvider()
