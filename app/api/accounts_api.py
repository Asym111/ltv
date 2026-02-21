# app/api/accounts.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from app.core.database import get_db
from app.core.security import normalize_phone, hash_password, verify_password
from app.models.auth import AuthUser, Tenant

router = APIRouter(prefix="/accounts", tags=["accounts"])


# ── Schemas ────────────────────────────────────────────────
class AccountUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    phone: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AccountUserCreate(BaseModel):
    phone: str = Field(..., min_length=5, max_length=32)
    name: str = Field(..., min_length=1, max_length=120)
    role: str = Field(default="staff")  # staff / admin / owner
    password: str = Field(..., min_length=4, max_length=128)


class AccountUserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=4, max_length=128)


class TenantProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool
    access_until: Optional[datetime] = None
    created_at: datetime


class TenantProfileUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=4, max_length=128)


# ── Helpers ────────────────────────────────────────────────
def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


def must_role(request: Request, *roles: str) -> dict:
    u = getattr(request.state, "user", None) or {}
    if not u:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if u.get("role") not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return u


ALLOWED_ROLES = {"owner", "admin", "staff"}


# ── Endpoints ──────────────────────────────────────────────

@router.get("/profile", response_model=TenantProfileOut)
def get_tenant_profile(request: Request, db: Session = Depends(get_db)):
    tenant_id = must_tenant_id(request)
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantProfileOut.model_validate(t)


@router.put("/profile", response_model=TenantProfileOut)
def update_tenant_profile(
    payload: TenantProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    must_role(request, "owner", "admin")
    tenant_id = must_tenant_id(request)
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    t.name = payload.name.strip()
    db.commit()
    db.refresh(t)
    return TenantProfileOut.model_validate(t)


@router.get("/users", response_model=List[AccountUserOut])
def list_users(request: Request, db: Session = Depends(get_db)):
    must_role(request, "owner", "admin")
    tenant_id = must_tenant_id(request)
    users = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id)
        .order_by(AuthUser.id.asc())
        .all()
    )
    return [AccountUserOut.model_validate(u) for u in users]


@router.post("/users", response_model=AccountUserOut)
def create_user(
    payload: AccountUserCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    must_role(request, "owner", "admin")
    tenant_id = must_tenant_id(request)
    current_role = (getattr(request.state, "user", None) or {}).get("role")

    # staff не может создавать owner
    role = payload.role if payload.role in ALLOWED_ROLES else "staff"
    if role == "owner" and current_role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can create another owner")

    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone")

    exists = db.query(AuthUser).filter(AuthUser.phone == phone).first()
    if exists:
        raise HTTPException(status_code=400, detail="Phone already registered")

    salt, pw_hash = hash_password(payload.password)
    u = AuthUser(
        tenant_id=tenant_id,
        phone=phone,
        name=payload.name.strip(),
        role=role,
        password_salt=salt,
        password_hash=pw_hash,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return AccountUserOut.model_validate(u)


@router.patch("/users/{user_id}", response_model=AccountUserOut)
def update_user(
    user_id: int,
    payload: AccountUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    must_role(request, "owner", "admin")
    tenant_id = must_tenant_id(request)
    current_user = getattr(request.state, "user", None) or {}

    u = db.query(AuthUser).filter(
        AuthUser.id == user_id,
        AuthUser.tenant_id == tenant_id,
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    # Нельзя менять роль owner если ты не owner
    if payload.role and payload.role == "owner" and current_user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only owner can assign owner role")

    if payload.name is not None:
        u.name = payload.name.strip()
    if payload.role is not None and payload.role in ALLOWED_ROLES:
        u.role = payload.role
    if payload.is_active is not None:
        # Нельзя деактивировать самого себя
        if u.id == current_user.get("id") and not payload.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        u.is_active = payload.is_active
    if payload.password:
        salt, pw_hash = hash_password(payload.password)
        u.password_salt = salt
        u.password_hash = pw_hash

    db.commit()
    db.refresh(u)
    return AccountUserOut.model_validate(u)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    must_role(request, "owner")
    tenant_id = must_tenant_id(request)
    current_user = getattr(request.state, "user", None) or {}

    u = db.query(AuthUser).filter(
        AuthUser.id == user_id,
        AuthUser.tenant_id == tenant_id,
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.id == current_user.get("id"):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db.delete(u)
    db.commit()
    return {"ok": True}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = getattr(request.state, "user", None) or {}
    uid = current_user.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    u = db.query(AuthUser).filter(AuthUser.id == int(uid)).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(payload.old_password, u.password_salt, u.password_hash):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")

    salt, pw_hash = hash_password(payload.new_password)
    u.password_salt = salt
    u.password_hash = pw_hash
    db.commit()
    return {"ok": True, "message": "Пароль изменён"}