# app/models/video.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean

from app.core.database import Base


class VideoResource(Base):
    __tablename__ = "video_resources"

    id          = Column(Integer, primary_key=True)
    tenant_id   = Column(Integer, nullable=True, index=True)  # None = глобальные (для всех)

    title       = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    youtube_url = Column(String(500), nullable=False)
    youtube_id  = Column(String(20),  nullable=False)   # извлекается из URL
    category    = Column(String(60),  nullable=False, default="general")
    tags        = Column(String(300), nullable=True)    # comma-separated

    is_active   = Column(Boolean, default=True, nullable=False)
    sort_order  = Column(Integer, default=0, nullable=False)

    added_by    = Column(Integer, nullable=True)   # auth_user.id
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)