from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict


Tier = Literal["Bronze", "Silver", "Gold"]
PaymentMethod = Literal["CASH", "CARD", "TRANSFER", "OTHER", "MIXED"]


class TransactionCreate(BaseModel):
    """
    Создание транзакции.
    Важно: поддерживаем автосоздание клиента (full_name, birth_date, tier).
    """
    model_config = ConfigDict(extra="forbid")

    user_phone: str = Field(..., min_length=5, max_length=32)

    amount: int = Field(..., gt=0, description="Сумма чека (в KZT, целое)")
    paid_amount: Optional[int] = Field(
        default=None,
        ge=0,
        description="Фактически оплачено. Если None — посчитаем автоматически."
    )

    redeem_points: int = Field(default=0, ge=0, description="Списать бонусов (поинты)")

    payment_method: PaymentMethod = Field(default="CASH")
    comment: str = Field(default="", max_length=255)

    # Поля для автосоздания клиента (если клиента нет)
    full_name: Optional[str] = Field(default=None, max_length=120)
    birth_date: Optional[date] = None
    tier: Optional[Tier] = Field(default=None)
    earn_rate: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Кастомный earn rate. Если None — по tier."
    )


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

    created_at: datetime
