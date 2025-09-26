from pydantic import BaseModel
from typing import Optional, List
import datetime

class SaleItem(BaseModel):
    product_id:str
    quantity: int
    cost_price: float
    selling_price: float
    profit: float

class Sale(BaseModel):
    id:str
    customer_id: Optional[str]
    items: List[SaleItem]
    payment_method:str
    total_amount: float
    total_profit: float
    crated_at:datetime