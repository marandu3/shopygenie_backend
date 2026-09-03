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
    if organization.sms_enabled and organization.sms_base_url and organization.sms_username and organization.sms_password_encrypted:
        password = decrypt_secret(organization.sms_password_encrypted)
        if password:
            return SMSGateProvider(
                base_url=organization.sms_base_url,
                username=organization.sms_username,
                password=password,
                device_id=organization.sms_device_id,
            )
    return ConsoleSMSProvider()
