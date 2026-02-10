# app/schemas/campaigns.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class CampaignCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    segment_key: str = Field(min_length=1, max_length=32)

    r_min: Optional[int] = Field(default=None, ge=1, le=5)
    f_min: Optional[int] = Field(default=None, ge=1, le=5)
    m_min: Optional[int] = Field(default=None, ge=1, le=5)
    q: Optional[str] = Field(default=None, max_length=80)
    sort: Optional[str] = Field(default=None, max_length=32)

    suggested_bonus: int = Field(default=0, ge=0, le=10_000_000)
    note: Optional[str] = Field(default=None, max_length=2000)


class CampaignOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    created_at: datetime

    name: str
    segment_key: str

    r_min: Optional[int] = None
    f_min: Optional[int] = None
    m_min: Optional[int] = None
    q: Optional[str] = None
    sort: Optional[str] = None

    suggested_bonus: int
    status: str
    recipients_total: int

    note: Optional[str] = None


class CampaignRecipientOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str
    full_name: Optional[str] = None
    tier: str = "Bronze"

    last_purchase_at: Optional[datetime] = None
    recency_days: int = 0

    purchases_90d: int = 0
    revenue_90d: int = 0

    purchases_total: int = 0
    revenue_total: int = 0

    r_score: int = 1
    f_score: int = 1
    m_score: int = 1
    rfm: str = "111"


class CampaignDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign: CampaignOut
    recipients_total: int
    recipients_preview: List[CampaignRecipientOut] = []

