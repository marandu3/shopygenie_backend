import logging

from app.integrations.sms.base import SMSProvider, SMSSendResult

logger = logging.getLogger("shopygenie")


class ConsoleSMSProvider(SMSProvider):
    """Used automatically when no SMSGate credentials are configured (local
    dev / this environment right now). Logs instead of sending so worker
    invitations and other SMS-triggering flows still work end-to-end without
    a live provider — never silently drops the message."""

    async def send(self, *, to: str, message: str) -> SMSSendResult:
        logger.info("sms_stub_send to=%s message=%r", to, message)
        return SMSSendResult(success=True, provider_message_id="console-stub")
