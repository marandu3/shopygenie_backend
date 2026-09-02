from functools import lru_cache

from app.core.config import get_settings
from app.integrations.sms.base import SMSProvider
from app.integrations.sms.console_provider import ConsoleSMSProvider
from app.integrations.sms.smsgate_provider import SMSGateProvider


@lru_cache
def get_sms_provider() -> SMSProvider:
    settings = get_settings()
    if settings.smsgate_base_url and settings.smsgate_api_key:
        return SMSGateProvider(
            base_url=settings.smsgate_base_url,
            api_key=settings.smsgate_api_key,
            sender_id=settings.smsgate_sender_id,
        )
    return ConsoleSMSProvider()
