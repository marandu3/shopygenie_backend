from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, timezone


class SaleItem(BaseModel):
    product_id: str
    product_name: Optional[str] = None  # fetched automatically
    quantity: int
    selling_price: float
    discount: float = 0.0
    total_price: float  # (selling_price - discount) × quantity


class CreateSale(BaseModel):
    customer_id: str
    items: List[SaleItem]
    payment_method: Literal["cash", "debt"]  # only two accepted values


class Sale(BaseModel):
    id: str
    customer_id: str
    customer_name: Optional[str] = None
    items: List[SaleItem]
    payment_method: Literal["cash", "debt"]
    total_amount: float
    created_at: datetime = datetime.now(timezone.utc)
