# app/api/accounts.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from app.core.database import get_db
from app.core.security import normalize_phone, hash_password, verify_password
from app.core.roles import ALL_ROLES
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
    role: str = Field(default="staff")
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
    is_setup_completed: bool
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


ALLOWED_ROLES = ALL_ROLES


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


# ── Setup Wizard ───────────────────────────────────────────

@router.get("/setup/status")
def get_setup_status(request: Request, db: Session = Depends(get_db)):
    """Проверяет, завершена ли первичная настройка тенанта."""
    tenant_id = must_tenant_id(request)
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"is_setup_completed": t.is_setup_completed}


@router.post("/setup/complete")
def complete_setup(request: Request, db: Session = Depends(get_db)):
    """Помечает настройку тенанта как завершённую."""
    must_role(request, "owner", "admin")
    tenant_id = must_tenant_id(request)
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    t.is_setup_completed = True
    db.commit()
    return {"ok": True, "message": "Setup completed"}


# ── Users ──────────────────────────────────────────────────

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

    if payload.name is not None:
        u.name = payload.name.strip()

    if payload.role is not None and payload.role in ALLOWED_ROLES:
        old_role = u.role
        if payload.role == "owner" and current_user.get("role") != "owner":
            raise HTTPException(status_code=403, detail="Only owner can assign owner role")
        u.role = payload.role
        if old_role != payload.role:
            # Invalidate all active sessions for this user so new role applies immediately
            u.session_version = (u.session_version or 1) + 1

    if payload.is_active is not None:
        if u.id == current_user.get("id") and not payload.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        if u.is_active != payload.is_active:
            u.is_active = payload.is_active
            # Force logout of active sessions on deactivation
            if not payload.is_active:
                u.session_version = (u.session_version or 1) + 1

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

    # По id из сессии: у владельца, переключённого в филиал, active tenant ≠ home tenant
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


# ── Филиалы (мультифилиальность) ───────────────────────────

class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool
    created_at: datetime


class BranchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class BranchUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    is_active: Optional[bool] = None


class SwitchTenantIn(BaseModel):
    tenant_id: int


def _home_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("home_tenant_id") or u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


@router.get("/branches")
def list_branches(request: Request, db: Session = Depends(get_db)):
    """Список филиалов сети + текущий контекст (для переключателя в шапке)."""
    must_role(request, "owner", "admin")
    home_id = _home_tenant_id(request)
    active_id = must_tenant_id(request)

    home = db.query(Tenant).filter(Tenant.id == home_id).first()
    if not home:
        raise HTTPException(status_code=404, detail="Tenant not found")

    is_root = home.parent_tenant_id is None
    branches: list[Tenant] = []
    if is_root:
        branches = (
            db.query(Tenant)
            .filter(Tenant.parent_tenant_id == home_id)
            .order_by(Tenant.id.asc())
            .all()
        )

    return {
        "is_root": is_root,
        "home_tenant_id": home_id,
        "home_name": home.name,
        "active_tenant_id": active_id,
        "branches": [BranchOut.model_validate(b).model_dump(mode="json") for b in branches],
    }


@router.post("/branches", response_model=BranchOut)
def create_branch(payload: BranchCreate, request: Request, db: Session = Depends(get_db)):
    """Создать филиал. Только владелец головного тенанта."""
    must_role(request, "owner")
    home_id = _home_tenant_id(request)

    home = db.query(Tenant).filter(Tenant.id == home_id).first()
    if not home:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if home.parent_tenant_id is not None:
        raise HTTPException(status_code=403, detail="Филиал не может создавать филиалы")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название филиала")

    branch = Tenant(
        name=name,
        parent_tenant_id=home_id,
        is_active=True,
        is_setup_completed=True,
        plan=home.plan or "branch",
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.patch("/branches/{branch_id}", response_model=BranchOut)
def update_branch(branch_id: int, payload: BranchUpdate, request: Request, db: Session = Depends(get_db)):
    must_role(request, "owner")
    home_id = _home_tenant_id(request)

    branch = db.query(Tenant).filter(
        Tenant.id == branch_id,
        Tenant.parent_tenant_id == home_id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Филиал не найден")

    if payload.name is not None:
        branch.name = payload.name.strip() or branch.name
    if payload.is_active is not None:
        branch.is_active = bool(payload.is_active)

    db.commit()
    db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.post("/switch-tenant")
def switch_tenant(payload: SwitchTenantIn, request: Request, db: Session = Depends(get_db)):
    """
    Переключить активный контекст на филиал (или обратно на головной офис).
    Доступно owner/admin головного тенанта.
    """
    must_role(request, "owner", "admin")
    home_id = _home_tenant_id(request)

    home = db.query(Tenant).filter(Tenant.id == home_id).first()
    if not home or home.parent_tenant_id is not None:
        raise HTTPException(status_code=403, detail="Переключение доступно только из головного офиса")

    target_id = int(payload.tenant_id)
    if target_id == home_id:
        target = home
    else:
        target = db.query(Tenant).filter(
            Tenant.id == target_id,
            Tenant.parent_tenant_id == home_id,
        ).first()
        if not target or not target.is_active:
            raise HTTPException(status_code=404, detail="Филиал не найден или отключён")

    request.session["active_tenant_id"] = target.id
    request.session["tenant_name"] = target.name
    return {"ok": True, "active_tenant_id": target.id, "tenant_name": target.name}
