from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import encrypt_field
from app.models.invite import Invite
from app.models.user import User

router = APIRouter(prefix="/invites", tags=["invites"])


class CreateInviteIn(BaseModel):
    role: str = Field(default="cashier", pattern="^(owner|admin|manager|cashier)$")
    phone: Optional[str] = Field(default=None, max_length=20)
    expires_hours: int = Field(default=48, ge=1, le=168)


class AcceptInviteIn(BaseModel):
    code: str = Field(..., min_length=8, max_length=64)
    full_name: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=6, max_length=100)


def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


def require_role(request: Request, *allowed: str):
    u = getattr(request.state, "user", None) or {}
    role = u.get("role", "")
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Access denied. Required roles: {allowed}")
    return u


@router.post("/create")
def create_invite(payload: CreateInviteIn, request: Request, db: Session = Depends(get_db)):
    tenant_id = must_tenant_id(request)
    user = require_role(request, "owner", "admin")

    code = secrets.token_urlsafe(16)
    expires_at = datetime.utcnow() + timedelta(hours=payload.expires_hours)

    invite = Invite(
        tenant_id=tenant_id,
        code=code,
        role=payload.role,
        phone=payload.phone,
        created_by=user.get("id", 0),
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    return {
        "ok": True,
        "code": invite.code,
        "role": invite.role,
        "expires_at": str(invite.expires_at),
        "url": f"/accept-invite?code={invite.code}",
    }


@router.post("/accept")
def accept_invite(payload: AcceptInviteIn, db: Session = Depends(get_db)):
    invite = db.query(Invite).filter(Invite.code == payload.code).first()

    if not invite:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    if invite.used_at:
        raise HTTPException(status_code=400, detail="Приглашение уже использовано")

    if datetime.utcnow() > invite.expires_at:
        raise HTTPException(status_code=400, detail="Срок действия приглашения истёк")

    invite_phone = invite.phone or ""
    if invite_phone:
        p_hash = hashlib.sha256(invite_phone.encode()).hexdigest()
        existing = db.query(User).filter(
            User.tenant_id == invite.tenant_id,
            User.phone_hash == p_hash,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Пользователь с таким телефоном уже существует")

    user = User(
        tenant_id=invite.tenant_id,
        phone=encrypt_field(invite_phone) if invite_phone else "",
        phone_hash=hashlib.sha256(invite_phone.encode()).hexdigest() if invite_phone else None,
        full_name=encrypt_field(payload.full_name),
        bonus_balance=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    invite.used_at = datetime.utcnow()
    db.commit()

    return {
        "ok": True,
        "user_id": user.id,
        "role": invite.role,
        "message": f"Пользователь {payload.full_name} успешно присоединился",
    }
