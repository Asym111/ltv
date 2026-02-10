from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


Tier = Literal["Bronze", "Silver", "Gold"]


class ClientMetricsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str
    full_name: Optional[str] = None
    tier: Tier = "Bronze"

    total_spent: int
    purchases_count: int
    avg_check: float

    bonus_balance: int
