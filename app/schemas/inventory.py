import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class InventoryMovementOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    branch_id: uuid.UUID | None
    movement_type: str
    quantity: int
    previous_quantity: int
    resulting_quantity: int
    reference_type: str | None
    reference_id: uuid.UUID | None
    reason: str | None
    performed_by: uuid.UUID
    created_at: datetime
