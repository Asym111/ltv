# app/services/campaigns.py
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.campaign import Campaign, CampaignRecipient
from app.services.analytics import list_clients_by_segment


def list_campaigns(db: Session) -> List[Campaign]:
    return db.query(Campaign).order_by(desc(Campaign.id)).all()


def create_campaign(db: Session, data: Dict) -> Campaign:
    c = Campaign(
        name=data["name"],
        segment_key=data["segment_key"],
        r_min=data.get("r_min"),
        f_min=data.get("f_min"),
        m_min=data.get("m_min"),
        q=data.get("q"),
        sort=data.get("sort"),
        suggested_bonus=int(data.get("suggested_bonus") or 0),
        note=data.get("note"),
        status="draft",
        recipients_total=0,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def get_campaign(db: Session, campaign_id: int) -> Optional[Campaign]:
    return db.query(Campaign).filter(Campaign.id == campaign_id).first()


def build_recipients(db: Session, campaign_id: int) -> Campaign:
    c = get_campaign(db, campaign_id)
    if not c:
        raise ValueError("Campaign not found")

    # берём ВСЕХ клиентов сегмента по фильтрам (большой лимит — внутренний вызов)
    res = list_clients_by_segment(
        db,
        key=c.segment_key,
        limit=100000,
        offset=0,
        r_min=c.r_min,
        f_min=c.f_min,
        m_min=c.m_min,
        q=c.q,
        sort=c.sort,
    )
    items = res.get("items") or []

    # очистка старого снапшота
    db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == c.id).delete(synchronize_session=False)

    # вставка
    for it in items:
        r = CampaignRecipient(
            campaign_id=c.id,
            phone=str(it.get("phone") or ""),
            full_name=it.get("full_name"),
            tier=str(it.get("tier") or "Bronze"),

            last_purchase_at=it.get("last_purchase_at"),
            recency_days=int(it.get("recency_days") or 0),

            purchases_90d=int(it.get("purchases_90d") or 0),
            revenue_90d=int(it.get("revenue_90d") or 0),

            purchases_total=int(it.get("purchases_total") or 0),
            revenue_total=int(it.get("revenue_total") or 0),

            r_score=int(it.get("r_score") or 1),
            f_score=int(it.get("f_score") or 1),
            m_score=int(it.get("m_score") or 1),
            rfm=str(it.get("rfm") or "111"),
        )
        db.add(r)

    c.recipients_total = int(len(items))
    c.status = "ready" if c.recipients_total > 0 else "draft"

    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def list_recipients(db: Session, campaign_id: int, limit: int = 200, offset: int = 0) -> List[CampaignRecipient]:
    return (
        db.query(CampaignRecipient)
        .filter(CampaignRecipient.campaign_id == campaign_id)
        .order_by(desc(CampaignRecipient.revenue_90d), desc(CampaignRecipient.purchases_90d))
        .offset(offset)
        .limit(limit)
        .all()
    )
