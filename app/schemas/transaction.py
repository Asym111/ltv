from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict


Tier = Literal["Bronze", "Silver", "Gold"]
PaymentMethod = Literal["CASH", "CARD", "TRANSFER", "OTHER", "MIXED"]


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_phone: str = Field(..., min_length=5, max_length=32)

    amount: int = Field(..., gt=0, description="Сумма чека (KZT, целое)")

    # Legacy name: gross discounted amount BEFORE loyalty redemption, not cash tender.
    paid_amount: Optional[int] = Field(default=None, ge=0, description="Сумма после скидки, ДО списания бонусов")
    manual_percent: Optional[Decimal] = Field(default=None, ge=0, le=100, decimal_places=2)
    request_id: Optional[UUID] = None

    redeem_points: int = Field(default=0, ge=0, description="Списать бонусов")
    # Галочка «Списать максимум»: сервер сам спишет min(доступно, % из настроек)
    redeem_all: bool = Field(default=False, description="Списать максимально разрешённое")

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
    request_id: Optional[UUID] = None
    comment: str = Field(default="", max_length=255)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_phone: Optional[str] = None

    amount: int
    paid_amount: int

    redeem_points: int
    earned_points: int
    earning_mode: Optional[str] = None
    earn_percent: Optional[Decimal] = None
    earn_base_amount: Optional[int] = None
    refunded_earned_points: int = 0
    refunded_redeem_points: int = 0

    payment_method: str
    comment: str

    status: str
    refunded_amount: int
    refunded_at: Optional[datetime] = None

    created_at: datetime


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: int
    amount: int
    earned_reversed: int
    redeemed_restored: int
    created_by_id: Optional[int] = None
    comment: str
    created_at: datetime


class RedeemPreviewOut(BaseModel):
    """Сколько бонусов можно списать на этот чек — для галочки «Списать максимум»."""
    found: bool
    earning_mode: Literal["automatic", "manual"] = "automatic"
    available: int = 0          # активные бонусы клиента
    pending: int = 0            # ещё не активированные
    redeem_max_percent: int = 0 # % от чека из настроек
    cap: int = 0                # лимит по проценту для этой суммы
    max_redeem: int = 0         # итог: min(available, cap)
