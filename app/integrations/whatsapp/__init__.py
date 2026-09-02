from app.integrations.whatsapp.console_provider import ConsoleWhatsAppProvider

__all__ = ["ConsoleWhatsAppProvider", "get_whatsapp_provider"]


def get_whatsapp_provider() -> ConsoleWhatsAppProvider:
    """No real WhatsApp Business API vendor is configured anywhere in this
    codebase (none was specified) — this is a console-logging stub, the same
    honest pattern used for SMS when no SMSGate credentials exist. Usage
    metering, quotas, and the send chokepoint are all real; only the actual
    network call to a WhatsApp provider is a stand-in. Swapping in a real
    provider later means adding one class here, per app/integrations/sms's
    provider-boundary pattern (MASTER PROMPT §78)."""
    return ConsoleWhatsAppProvider()
