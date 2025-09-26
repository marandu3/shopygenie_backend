from pydantic import BaseModel
from typing import Optional
import datetime

class Customer(BaseModel):
    id: str
    name:str
    phone:str
    address: Optional[str]
    balance: float=0
    created_at: datetime