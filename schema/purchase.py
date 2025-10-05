from datetime import datetime , timezone
from typing import List, Optional
from pydantic import BaseModel, EmailStr

class PurchaseItem(BaseModel):
    product_id:str
    quantity: int
    cost_price: float
    total_cost: float

class Purchase(BaseModel):
    id:str
    supplier: Optional[str] = None
    items: List[PurchaseItem]
    total_amount: float
    purchased_by: str
    created_at: datetime = datetime.now(timezone.utc)