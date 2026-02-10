# app/schemas/settings.py
from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int

    earn_bronze_percent: int = Field(ge=0, le=100)
    earn_silver_percent: int = Field(ge=0, le=100)
    earn_gold_percent: int = Field(ge=0, le=100)

    redeem_max_percent: int = Field(ge=0, le=100)

    activation_days: int = Field(ge=0, le=3650)
    burn_days: int = Field(ge=0, le=3650)

    birthday_bonus_amount: int = Field(ge=0, le=10_000_000)
    birthday_bonus_days_before: int = Field(ge=0, le=31)
    birthday_bonus_ttl_days: int = Field(ge=0, le=3650)


class SettingsUpdate(BaseModel):
    """
    Полное обновление настроек (PUT).
    """
    model_config = ConfigDict(extra="forbid")

    earn_bronze_percent: int = Field(ge=0, le=100)
    earn_silver_percent: int = Field(ge=0, le=100)
    earn_gold_percent: int = Field(ge=0, le=100)

    redeem_max_percent: int = Field(ge=0, le=100)

    activation_days: int = Field(ge=0, le=3650)
    burn_days: int = Field(ge=0, le=3650)

    birthday_bonus_amount: int = Field(ge=0, le=10_000_000)
    birthday_bonus_days_before: int = Field(ge=0, le=31)
    birthday_bonus_ttl_days: int = Field(ge=0, le=3650)
