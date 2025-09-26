from pydantic import BaseModel, EmailStr
import datetime
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
    created_at: datetime