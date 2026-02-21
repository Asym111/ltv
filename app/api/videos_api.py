# app/api/videos.py
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.video_model import VideoResource

router = APIRouter(prefix="/videos", tags=["videos"])

# ── YouTube ID extractor ───────────────────────────────────
_YT_PATTERNS = [
    re.compile(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})"),
]

def extract_youtube_id(url: str) -> str | None:
    for p in _YT_PATTERNS:
        m = p.search(url or "")
        if m:
            return m.group(1)
    return None

def thumbnail_url(yt_id: str) -> str:
    return f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg"


# ── Schemas ────────────────────────────────────────────────
CATEGORIES = [
    "general", "loyalty", "marketing", "analytics",
    "crm", "campaigns", "settings", "other",
]

CATEGORY_LABELS = {
    "general":   "Общее",
    "loyalty":   "Лояльность",
    "marketing": "Маркетинг",
    "analytics": "Аналитика",
    "crm":       "CRM",
    "campaigns": "Кампании",
    "settings":  "Настройки",
    "other":     "Другое",
}


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:          int
    title:       str
    description: Optional[str]
    youtube_url: str
    youtube_id:  str
    thumbnail:   str
    category:    str
    category_label: str
    tags:        Optional[str]
    is_active:   bool
    sort_order:  int
    created_at:  datetime

    @classmethod
    def from_orm_ext(cls, v: VideoResource) -> "VideoOut":
        return cls(
            id=v.id,
            title=v.title,
            description=v.description,
            youtube_url=v.youtube_url,
            youtube_id=v.youtube_id,
            thumbnail=thumbnail_url(v.youtube_id),
            category=v.category,
            category_label=CATEGORY_LABELS.get(v.category, v.category),
            tags=v.tags,
            is_active=v.is_active,
            sort_order=v.sort_order,
            created_at=v.created_at,
        )


class VideoCreate(BaseModel):
    title:       str  = Field(..., min_length=1, max_length=200)
    youtube_url: str  = Field(..., min_length=10, max_length=500)
    description: Optional[str] = Field(default=None, max_length=1000)
    category:    str  = Field(default="general")
    tags:        Optional[str] = Field(default=None, max_length=300)
    sort_order:  int  = Field(default=0, ge=0)


class VideoUpdate(BaseModel):
    title:       Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    category:    Optional[str] = None
    tags:        Optional[str] = Field(default=None, max_length=300)
    is_active:   Optional[bool] = None
    sort_order:  Optional[int]  = Field(default=None, ge=0)


# ── Helpers ────────────────────────────────────────────────
def get_tenant_id(request: Request) -> int | None:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    return int(tid) if tid else None


# ── Endpoints ──────────────────────────────────────────────
@router.get("/", response_model=List[VideoOut])
def list_videos(
    request: Request,
    category: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
) -> List[VideoOut]:
    tenant_id = get_tenant_id(request)

    # Глобальные (tenant_id=None) + свои
    from sqlalchemy import or_
    qr = db.query(VideoResource).filter(
        VideoResource.is_active == True,
        or_(
            VideoResource.tenant_id == None,
            VideoResource.tenant_id == tenant_id,
        )
    )

    if category:
        qr = qr.filter(VideoResource.category == category)

    if q:
        q_low = f"%{q.lower()}%"
        from sqlalchemy import func
        qr = qr.filter(
            VideoResource.title.ilike(q_low) |
            VideoResource.tags.ilike(q_low)
        )

    videos = qr.order_by(VideoResource.sort_order.asc(), VideoResource.id.desc()).all()
    return [VideoOut.from_orm_ext(v) for v in videos]


@router.post("/", response_model=VideoOut)
def create_video(
    payload: VideoCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> VideoOut:
    u = getattr(request.state, "user", None) or {}
    role = u.get("role", "")
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can add videos")

    yt_id = extract_youtube_id(payload.youtube_url)
    if not yt_id:
        raise HTTPException(status_code=400, detail="Не удалось извлечь YouTube ID из ссылки")

    category = payload.category if payload.category in CATEGORIES else "general"
    tenant_id = get_tenant_id(request)

    v = VideoResource(
        tenant_id=tenant_id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        youtube_url=payload.youtube_url.strip(),
        youtube_id=yt_id,
        category=category,
        tags=payload.tags,
        sort_order=payload.sort_order,
        is_active=True,
        added_by=u.get("id"),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return VideoOut.from_orm_ext(v)


@router.patch("/{video_id}", response_model=VideoOut)
def update_video(
    video_id: int,
    payload: VideoUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> VideoOut:
    u = getattr(request.state, "user", None) or {}
    if u.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can edit videos")

    v = db.query(VideoResource).filter(VideoResource.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Video not found")

    if payload.title       is not None: v.title       = payload.title.strip()
    if payload.description is not None: v.description = payload.description.strip() or None
    if payload.category    is not None: v.category    = payload.category if payload.category in CATEGORIES else v.category
    if payload.tags        is not None: v.tags        = payload.tags
    if payload.is_active   is not None: v.is_active   = payload.is_active
    if payload.sort_order  is not None: v.sort_order  = payload.sort_order

    db.commit()
    db.refresh(v)
    return VideoOut.from_orm_ext(v)


@router.delete("/{video_id}")
def delete_video(
    video_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    u = getattr(request.state, "user", None) or {}
    if u.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can delete videos")

    v = db.query(VideoResource).filter(VideoResource.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Video not found")

    db.delete(v)
    db.commit()
    return {"ok": True}


@router.get("/categories")
def list_categories() -> dict:
    return {"categories": [
        {"key": k, "label": v} for k, v in CATEGORY_LABELS.items()
    ]}