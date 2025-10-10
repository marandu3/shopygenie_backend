from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone

class DebtPayment(BaseModel):
    amount: float
    date: datetime
    method: str  # e.g., "cash", "transfer"

class Debt(BaseModel):
    id: str
    customer_name: str
    sale_id: str
    amount: float
    balance: float
    cleared: bool = False
    payment: List[DebtPayment] = []
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: Optional[datetime] = None
