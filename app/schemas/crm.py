from __future__ import annotations

from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


KNOWN_TIERS = {"Bronze", "Silver", "Gold"}


class ClientMetricsOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phone: str
    full_name: Optional[str] = None
    tier: str = "Bronze"
    birth_date: Optional[date] = None

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier(cls, v: str) -> str:
        return str(v) if v else "Bronze"

    total_spent: int
    purchases_count: int
    avg_check: float

    bonus_balance: int
    pending_balance: int = 0