from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone


class Expenditure(BaseModel):
    id: str  # ID will be a string
    description: str
    amount: float
    date: datetime = datetime.now(timezone.utc)
    category: Optional[str] = "general"  # default category
    created_at: Optional[datetime] = datetime.now(timezone.utc)
