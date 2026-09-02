from app.integrations.sms import get_sms_provider


async def send_sms(*, to: str, message: str) -> None:
    """Single chokepoint every SMS-triggering flow calls through. Business
    logic never talks to the SMS provider directly (MASTER PROMPT §39)."""
    provider = get_sms_provider()
    await provider.send(to=to, message=message)
