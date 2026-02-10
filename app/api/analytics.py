# app/api/analytics.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.analytics import AnalyticsOverviewOut, AnalyticsSegmentClientsOut
from app.services.analytics import build_analytics_overview, list_clients_by_segment

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverviewOut)
def analytics_overview(db: Session = Depends(get_db)) -> AnalyticsOverviewOut:
    data = build_analytics_overview(db)
    return AnalyticsOverviewOut.model_validate(data)


@router.get("/segment/{key}", response_model=AnalyticsSegmentClientsOut)
def analytics_segment_clients(
    key: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    r_min: int | None = Query(default=None, ge=1, le=5),
    f_min: int | None = Query(default=None, ge=1, le=5),
    m_min: int | None = Query(default=None, ge=1, le=5),
    q: str | None = Query(default=None, max_length=80),
    sort: str | None = Query(default=None, max_length=32),
    db: Session = Depends(get_db),
) -> AnalyticsSegmentClientsOut:
    data = list_clients_by_segment(
        db,
        key=key,
        limit=limit,
        offset=offset,
        r_min=r_min,
        f_min=f_min,
        m_min=m_min,
        q=q,
        sort=sort,
    )
    return AnalyticsSegmentClientsOut.model_validate(data)
