from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.transaction import PaymentMethod
from app.schemas.transaction import RefundOut


Scope = Literal["balance:read", "transactions:read", "transactions:write", "refunds:write"]


class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    tenant_id: int | None = Field(default=None, gt=0)
    expires_in_days: int = Field(default=90, ge=1, le=365)
    scopes: list[Scope] = Field(default_factory=lambda: ["balance:read", "transactions:read", "transactions:write"], min_length=1, max_length=4)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("Укажите название ключа")
        return value.strip()

    @field_validator("scopes")
    @classmethod
    def unique_scopes(cls, value):
        return sorted(set(value))


class KeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    public_id: str
    name: str
    tenant_id: int
    network_id: int
    scopes: list[Scope]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class KeyCreated(BaseModel):
    key: KeyOut
    token: str


class BalanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(min_length=5, max_length=32)
    amount: int = Field(default=0, ge=0, le=2147483647)


class PurchaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    request_id: UUID
    phone: str = Field(min_length=5, max_length=32)
    amount: int = Field(gt=0, le=2147483647, description="Сумма после скидки, ДО списания бонусов, KZT")
    redeem_points: int = Field(default=0, ge=0, le=2147483647)
    manual_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    payment_method: PaymentMethod = "CASH"
    full_name: str | None = Field(default=None, max_length=120)
    birth_date: date | None = None
    comment: str = Field(default="", max_length=255)


class RefundIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    request_id: UUID
    full_refund: bool = False
    amount: int | None = Field(default=None, gt=0, le=2147483647)
    comment: str = Field(default="", max_length=255)


class BalanceOut(BaseModel):
    found: bool
    phone: str
    available: int
    pending: int
    total: int
    earning_mode: Literal["automatic", "manual"]
    redeem_max_percent: int
    max_redeem: int


class IntegrationTransactionOut(BaseModel):
    id: int
    external_id: str | None
    status: str
    amount: int
    cash_amount: int
    redeem_points: int
    earned_points: int
    earning_mode: str | None
    earn_percent: Decimal | None
    earn_base_amount: int | None
    refunded_amount: int
    refundable_amount: int
    refunded_earned_points: int
    refunded_redeem_points: int
    replayed: bool = False


class IntegrationRefundOut(RefundOut):
    external_id: str | None


class RefundResponse(BaseModel):
    transaction: IntegrationTransactionOut
    refund: IntegrationRefundOut
    replayed: bool
