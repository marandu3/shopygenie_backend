from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SMSSendResult:
    success: bool
    provider_message_id: str | None
    error: str | None = None


class SMSProvider(ABC):
    """Provider-agnostic SMS boundary (MASTER PROMPT §39).

    Business logic (worker invites, receipts, debt reminders, ...) must only
    ever depend on this interface — never on a specific vendor's SDK/HTTP
    shape. Swapping SMSGate for another provider means adding one new class
    here, nothing else in the codebase changes.
    """

    @abstractmethod
    async def send(self, *, to: str, message: str) -> SMSSendResult: ...
