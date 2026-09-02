import logging

logger = logging.getLogger("shopygenie")


class ConsoleWhatsAppProvider:
    async def send(self, *, to: str, message: str) -> bool:
        logger.info("whatsapp_stub_send to=%s message=%r", to, message)
        return True
