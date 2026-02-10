from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field, ConfigDict


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(..., min_length=5, max_length=30)
    full_name: str | None = None
    birth_date: date | None = None
    tier: str | None = "Bronze"
    bonus_balance: int = Field(default=0, ge=0)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    birth_date: date | None = None
    tier: str | None = None
    bonus_balance: int | None = Field(default=None, ge=0)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    full_name: str | None
    birth_date: date | None
    tier: str
    bonus_balance: int
    created_at: datetime
