from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel


class ProductSchema(BaseModel):
    id: str
    name: str
    category: str
    unit: str
    cost_price: float
    selling_price: float
    current_stock: int
    low_stock_alert: Optional[int] = None
    supplier: Optional[str] = None
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)

    model_config = {
        "arbitrary_types_allowed": True
    }
