import logging

import httpx

from app.integrations.sms.base import SMSProvider, SMSSendResult

logger = logging.getLogger("shopygenie")


class SMSGateProvider(SMSProvider):
    """Real adapter for the SMSGate API.

    NOTE: the exact request/response shape below is a reasonable default
    (bearer auth, JSON body of {to, message, sender_id}) but has not been
    verified against SMSGate's actual API docs/credentials — verify the
    endpoint path and payload field names against your SMSGate account
    before relying on this in production, then adjust `_build_request`.
    """

    def __init__(self, base_url: str, api_key: str, sender_id: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._sender_id = sender_id

    async def send(self, *, to: str, message: str) -> SMSSendResult:
        url = f"{self._base_url}/messages"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {"to": to, "message": message, "sender_id": self._sender_id}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return SMSSendResult(success=True, provider_message_id=data.get("id"))
        except httpx.HTTPError as exc:
            logger.warning("smsgate_send_failed to=%s error=%s", to, exc)
            return SMSSendResult(success=False, provider_message_id=None, error=str(exc))
