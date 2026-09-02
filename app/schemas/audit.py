import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class AuditLogOut(ORMModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    acting_as_platform_owner: bool
    action: str
    resource_type: str
    resource_id: str | None
    reason: str | None
    metadata_json: dict | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
