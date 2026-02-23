# app/models/campaign.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id              = Column(Integer, primary_key=True, index=True)
    tenant_id       = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)  # ← добавлено
    name            = Column(String(200), nullable=False)
    segment_key     = Column(String(50), nullable=False, default="all")
    r_min           = Column(Integer, nullable=True)
    f_min           = Column(Integer, nullable=True)
    m_min           = Column(Integer, nullable=True)
    q               = Column(String(80), nullable=True)
    sort            = Column(String(32), nullable=True)
    suggested_bonus = Column(Integer, default=0, nullable=False)
    note            = Column(Text, nullable=True)
    status          = Column(String(20), default="draft", nullable=False)
    recipients_total = Column(Integer, default=0, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)

    recipients = relationship("CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id              = Column(Integer, primary_key=True, index=True)
    campaign_id     = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    phone           = Column(String(32), nullable=False)
    full_name       = Column(String(120), nullable=True)
    tier            = Column(String(20), nullable=True)
    last_purchase_at = Column(DateTime, nullable=True)
    recency_days    = Column(Integer, default=0)
    purchases_90d   = Column(Integer, default=0)
    revenue_90d     = Column(Integer, default=0)
    purchases_total = Column(Integer, default=0)
    revenue_total   = Column(Integer, default=0)
    r_score         = Column(Integer, default=1)
    f_score         = Column(Integer, default=1)
    m_score         = Column(Integer, default=1)
    rfm             = Column(String(10), default="111")

    campaign = relationship("Campaign", back_populates="recipients")