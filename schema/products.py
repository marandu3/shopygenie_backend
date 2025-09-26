import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

class productSchema(BaseModel):
    id:str
    name : str
    category : str
    unit: str
    cost_price : float
    selling_price : float
    current_stock : int
    low_stock_alert : Optional[int] = None
    supplier: Optional[str] = None
    created_at: datetime
    updated_at: datetime

