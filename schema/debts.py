from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
from typing import List

class DebtPayment(BaseModel):
    amount: float
    date: datetime
    method: str

class Debt(BaseModel):
    id:str
    customer_name:str
    sale_id:str
    amount:float
    cleared:bool=False
    balance:float
    payment: List[DebtPayment]=[]
    created_at: datetime = datetime.now(timezone.utc)