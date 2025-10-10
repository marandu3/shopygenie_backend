# schema/purchase.py
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel


class PurchaseItem(BaseModel):
    product_id: str
    quantity: int
    # These will be auto-filled from product details, so they don’t need to be entered by the user
    cost_price: Optional[float] = None
    total_cost: Optional[float] = None
    product_name: Optional[str] = None  # for easier reporting/lookup


class Purchase(BaseModel):
    id: str
    supplier: Optional[str] = None
    items: List[PurchaseItem]
    total_amount: Optional[float] = 0.0
    purchased_by: str
    created_at: datetime = datetime.now(timezone.utc)
