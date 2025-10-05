from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

class Customer(BaseModel):
    id: str
    name:str
    phone:str
    address: Optional[str]
    balance: float=0
    created_at: datetime =datetime.now(timezone.utc)