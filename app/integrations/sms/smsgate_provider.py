import logging

import httpx

from app.integrations.sms.base import SMSProvider, SMSSendResult

logger = logging.getLogger("shopygenie")


class SMSGateProvider(SMSProvider):
    """Adapter for SMSGate (sms-gate.app) — an Android-phone-as-SMS-gateway
    service. Auths with HTTP Basic (username/password created in the
    SMSGate app or its cloud console) and targets one specific registered
    device by device_id. Endpoint/payload shape follows the documented
    3rdparty API (POST {base_url}/message, base_url typically ending in
    .../3rdparty/v1) — verify against your account if SMSGate changes it.
    """

    def __init__(self, base_url: str, username: str, password: str, device_id: str | None = None):
        self._base_url = base_url.rstrip("/")
        self._auth = httpx.BasicAuth(username, password)
        self._device_id = device_id or None

    async def send(self, *, to: str, message: str) -> SMSSendResult:
        url = f"{self._base_url}/message"
        payload: dict = {"message": message, "phoneNumbers": [to]}
        if self._device_id:
            payload["deviceId"] = self._device_id

        try:
            async with httpx.AsyncClient(timeout=10.0, auth=self._auth) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return SMSSendResult(success=True, provider_message_id=data.get("id"))
        except httpx.HTTPError as exc:
            logger.warning("smsgate_send_failed to=%s error=%s", to, exc)
            return SMSSendResult(success=False, provider_message_id=None, error=str(exc))
