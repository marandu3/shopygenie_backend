from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone 

class SaleItem(BaseModel):
    product_id:str
    quantity: int
    cost_price: float
    selling_price: float
    profit: float

class create_Sale(BaseModel):
    customer_id: Optional[str]
    items: List[SaleItem]
    payment_method:str
    total_amount: float
    total_profit: float
    crated_at:datetime = datetime.now(timezone.utc)

class Sale(BaseModel):
    id:str
    