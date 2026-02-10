from datetime import datetime
from pydantic import BaseModel, Field


class BonusOut(BaseModel):
    id: int
    user_id: int
    delta: float
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class BonusBalanceOut(BaseModel):
    user_id: int
    balance: float
    updated_at: datetime
