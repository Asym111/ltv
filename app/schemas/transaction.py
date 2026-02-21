from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict


Tier = Literal["Bronze", "Silver", "Gold"]
PaymentMethod = Literal["CASH", "CARD", "TRANSFER", "OTHER", "MIXED"]


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_phone: str = Field(..., min_length=5, max_length=32)

    amount: int = Field(..., gt=0, description="Сумма чека (KZT, целое)")

    # ✅ В UI поле «Оплачено» убираем, но API оставим совместимым
    paid_amount: Optional[int] = Field(default=None, ge=0)

    redeem_points: int = Field(default=0, ge=0, description="Списать бонусов")

    payment_method: PaymentMethod = Field(default="CASH")
    comment: str = Field(default="", max_length=255)

    full_name: Optional[str] = Field(default=None, max_length=120)
    birth_date: Optional[date] = None
    tier: Optional[Tier] = Field(default=None)


class TransactionRefund(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Если full_refund=True — amount игнорируем
    amount: Optional[int] = Field(default=None, ge=1, description="Сумма возврата (KZT)")
    full_refund: bool = False
    comment: str = Field(default="", max_length=255)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_phone: Optional[str] = None

    amount: int
    paid_amount: int

    redeem_points: int
    earned_points: int

    payment_method: str
    comment: str

    status: str
    refunded_amount: int
    refunded_at: Optional[datetime] = None

    created_at: datetime
