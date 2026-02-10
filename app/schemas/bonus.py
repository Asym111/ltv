from datetime import datetime
from pydantic import BaseModel


class BonusLedgerOut(BaseModel):
    id: int
    user_id: int
    delta: float
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class BonusBalanceOut(BaseModel):
    phone: str
    bonus_balance: float


class ClientCardOut(BaseModel):
    phone: str
    full_name: str | None = None
    loyalty_tier: str = "Bronze"

    total_spent: float = 0.0
    purchases_count: int = 0
    avg_check: float = 0.0
    bonus_balance: float = 0.0

    is_birthday_today: bool = False
