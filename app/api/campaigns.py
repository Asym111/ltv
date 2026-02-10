# app/api/campaigns.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.campaigns import CampaignCreateIn, CampaignOut, CampaignDetailOut, CampaignRecipientOut
from app.services.campaigns import list_campaigns, create_campaign, get_campaign, build_recipients, list_recipients

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/", response_model=list[CampaignOut])
def campaigns_list(db: Session = Depends(get_db)) -> list[CampaignOut]:
    rows = list_campaigns(db)
    return [CampaignOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/", response_model=CampaignOut)
def campaigns_create(payload: CampaignCreateIn, db: Session = Depends(get_db)) -> CampaignOut:
    c = create_campaign(db, payload.model_dump())
    return CampaignOut.model_validate(c, from_attributes=True)


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
def campaigns_get(campaign_id: int, db: Session = Depends(get_db)) -> CampaignDetailOut:
    c = get_campaign(db, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    recs = list_recipients(db, campaign_id=campaign_id, limit=50, offset=0)
    preview = [
        CampaignRecipientOut(
            phone=r.phone,
            full_name=r.full_name,
            tier=r.tier,
            last_purchase_at=r.last_purchase_at,
            recency_days=r.recency_days,
            purchases_90d=r.purchases_90d,
            revenue_90d=r.revenue_90d,
            purchases_total=r.purchases_total,
            revenue_total=r.revenue_total,
            r_score=r.r_score,
            f_score=r.f_score,
            m_score=r.m_score,
            rfm=r.rfm,
        )
        for r in recs
    ]

    return CampaignDetailOut(
        campaign=CampaignOut.model_validate(c, from_attributes=True),
        recipients_total=c.recipients_total,
        recipients_preview=preview,
    )


@router.post("/{campaign_id}/build", response_model=CampaignOut)
def campaigns_build(campaign_id: int, db: Session = Depends(get_db)) -> CampaignOut:
    try:
        c = build_recipients(db, campaign_id)
        return CampaignOut.model_validate(c, from_attributes=True)
    except ValueError:
        raise HTTPException(status_code=404, detail="Campaign not found")


@router.get("/{campaign_id}/recipients", response_model=list[CampaignRecipientOut])
def campaigns_recipients(
    campaign_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[CampaignRecipientOut]:
    c = get_campaign(db, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    rows = list_recipients(db, campaign_id=campaign_id, limit=limit, offset=offset)
    return [
        CampaignRecipientOut(
            phone=r.phone,
            full_name=r.full_name,
            tier=r.tier,
            last_purchase_at=r.last_purchase_at,
            recency_days=r.recency_days,
            purchases_90d=r.purchases_90d,
            revenue_90d=r.revenue_90d,
            purchases_total=r.purchases_total,
            revenue_total=r.revenue_total,
            r_score=r.r_score,
            f_score=r.f_score,
            m_score=r.m_score,
            rfm=r.rfm,
        )
        for r in rows
    ]

