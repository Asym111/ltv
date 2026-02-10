# app/models/campaign.py
from __future__ import annotations

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    name = Column(String(120), nullable=False)

    segment_key = Column(String(32), nullable=False)

    r_min = Column(Integer, nullable=True)
    f_min = Column(Integer, nullable=True)
    m_min = Column(Integer, nullable=True)
    q = Column(String(80), nullable=True)
    sort = Column(String(32), nullable=True)

    suggested_bonus = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="draft")  # draft/ready/sent/archived

    recipients_total = Column(Integer, nullable=False, default=0)
    note = Column(Text, nullable=True)

    recipients = relationship(
        "CampaignRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    phone = Column(String(16), nullable=False, index=True)
    full_name = Column(String(120), nullable=True)
    tier = Column(String(16), nullable=False, default="Bronze")

    last_purchase_at = Column(DateTime(timezone=False), nullable=True)
    recency_days = Column(Integer, nullable=False, default=0)

    purchases_90d = Column(Integer, nullable=False, default=0)
    revenue_90d = Column(Integer, nullable=False, default=0)

    purchases_total = Column(Integer, nullable=False, default=0)
    revenue_total = Column(Integer, nullable=False, default=0)

    r_score = Column(Integer, nullable=False, default=1)
    f_score = Column(Integer, nullable=False, default=1)
    m_score = Column(Integer, nullable=False, default=1)
    rfm = Column(String(8), nullable=False, default="111")

    campaign = relationship("Campaign", back_populates="recipients")
