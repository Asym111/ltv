# app/schemas/analytics.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, ConfigDict


AlertLevel = Literal["info", "warning", "danger"]


class AnalyticsWindowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int
    label: str
    revenue: int
    transactions: int
    clients: int
    avg_check: float


class AnalyticsSegmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    hint: str
    clients: int


class AnalyticsAlertOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    level: AlertLevel = "info"
    count: int = 0
    hint: str = ""
    href: str = ""


class AnalyticsOverviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    windows: List[AnalyticsWindowOut]
    segments: List[AnalyticsSegmentOut]
    alerts: List[AnalyticsAlertOut]

    clients_total: int
    users_with_tx: int
    total_spent: int


class AnalyticsSegmentClientOut(BaseModel):
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


class AnalyticsSegmentClientsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_key: str
    segment_title: str
    total: int
    items: List[AnalyticsSegmentClientOut]
    generated_at: datetime

    filters: dict
    rfm_scoring: str
