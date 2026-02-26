from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


KNOWN_TIERS = {"Bronze", "Silver", "Gold"}


class ClientMetricsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str
    full_name: Optional[str] = None
    tier: str = "Bronze"

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier(cls, v: str) -> str:
        """Если тир не стандартный (кастомный уровень) — возвращаем Bronze"""
        return v if v in KNOWN_TIERS else "Bronze"

    total_spent: int
    purchases_count: int
    avg_check: float

    bonus_balance: int