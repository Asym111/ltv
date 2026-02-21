# app/web/superadmin.py
"""
Суперадмин панель — управление всеми tenant-ами.
Доступ: /superadmin/login (логин/пароль из .env)
Защита: отдельная сессия, не пересекается с обычными пользователями.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.security import normalize_phone, hash_password
from app.models.auth import Tenant, AuthUser
from app.models.user import User
from app.models.transaction import Transaction

router = APIRouter(prefix="/superadmin")

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── Конфиг из .env ────────────────────────────────────────────
def _sa_login() -> str:
    return (os.getenv("SUPERADMIN_LOGIN", "") or "").strip()

def _sa_password() -> str:
    return (os.getenv("SUPERADMIN_PASSWORD", "") or "").strip()

# ── Auth helpers ──────────────────────────────────────────────
def _is_authed(request: Request) -> bool:
    return request.session.get("_sa_authed") is True

def _require_auth(request: Request):
    """Возвращает RedirectResponse если не авторизован, иначе None."""
    if not _is_authed(request):
        return RedirectResponse(url="/superadmin/login", status_code=303)
    return None

# ── Статистика по tenant ──────────────────────────────────────
def _tenant_stats(db, tenant_id: int) -> dict:
    now = datetime.utcnow()
    d30 = now - timedelta(days=30)

    users_count = db.scalar(
        select(func.count(User.id)).where(User.tenant_id == tenant_id)
    ) or 0

    txn_count = db.scalar(
        select(func.count(Transaction.id)).where(Transaction.tenant_id == tenant_id)
    ) or 0

    revenue_30d = db.scalar(
        select(func.coalesce(func.sum(Transaction.paid_amount), 0)).where(
            Transaction.tenant_id == tenant_id,
            Transaction.created_at >= d30,
            Transaction.status == "completed",
        )
    ) or 0

    txn_30d = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.tenant_id == tenant_id,
            Transaction.created_at >= d30,
        )
    ) or 0

    owner = db.scalar(
        select(AuthUser).where(
            AuthUser.tenant_id == tenant_id,
            AuthUser.role == "owner",
        )
    )

    return {
        "users_count": users_count,
        "txn_count": txn_count,
        "revenue_30d": revenue_30d,
        "txn_30d": txn_30d,
        "owner_phone": owner.phone if owner else "—",
        "owner_name": owner.name if owner else "—",
    }


# ══════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════

@router.get("/login", response_class=HTMLResponse)
def sa_login_page(request: Request, error: str = ""):
    if _is_authed(request):
        return RedirectResponse(url="/superadmin", status_code=303)
    return templates.TemplateResponse(
        "superadmin/login.html",
        {"request": request, "error": error},
    )


@router.post("/login")
def sa_login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    expected_login = _sa_login()
    expected_password = _sa_password()

    if not expected_login or not expected_password:
        return templates.TemplateResponse(
            "superadmin/login.html",
            {"request": request, "error": "SUPERADMIN_LOGIN/PASSWORD не настроены в .env"},
        )

    if login.strip() == expected_login and password == expected_password:
        request.session["_sa_authed"] = True
        return RedirectResponse(url="/superadmin", status_code=303)

    return templates.TemplateResponse(
        "superadmin/login.html",
        {"request": request, "error": "Неверный логин или пароль"},
    )


@router.get("/logout")
def sa_logout(request: Request):
    request.session.pop("_sa_authed", None)
    return RedirectResponse(url="/superadmin/login", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def sa_dashboard(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).order_by(Tenant.id.desc()).all()
        now = datetime.utcnow()

        rows = []
        for t in tenants:
            stats = _tenant_stats(db, t.id)
            auth_users = db.scalar(
                select(func.count(AuthUser.id)).where(AuthUser.tenant_id == t.id)
            ) or 0

            # Статус подписки
            if not t.is_active:
                sub_status = "disabled"
            elif t.access_until is None:
                sub_status = "unlimited"
            elif t.access_until < now:
                sub_status = "expired"
            elif t.access_until < now + timedelta(days=7):
                sub_status = "expiring"
            else:
                sub_status = "active"

            rows.append({
                "tenant": t,
                "sub_status": sub_status,
                "auth_users": auth_users,
                **stats,
            })

        # Общие цифры
        total_tenants = len(tenants)
        active_tenants = sum(1 for r in rows if r["sub_status"] in ("active", "unlimited"))
        total_users = sum(r["users_count"] for r in rows)
        total_revenue_30d = sum(r["revenue_30d"] for r in rows)

        return templates.TemplateResponse(
            "superadmin/dashboard.html",
            {
                "request": request,
                "rows": rows,
                "now": now,
                "total_tenants": total_tenants,
                "active_tenants": active_tenants,
                "total_users": total_users,
                "total_revenue_30d": total_revenue_30d,
            },
        )
    finally:
        db.close()


@router.post("/tenants/create")
def sa_create_tenant(
    request: Request,
    name: str = Form(...),
    owner_phone: str = Form(...),
    owner_password: str = Form(...),
    owner_name: str = Form("Owner"),
    grant_days: int = Form(30),
    plan: str = Form("trial"),
):
    redir = _require_auth(request)
    if redir:
        return redir

    db = SessionLocal()
    try:
        t = Tenant(
            name=name.strip() or "Account",
            is_active=True,
            access_until=None,
            plan=plan,
        )
        if grant_days > 0:
            t.access_until = datetime.utcnow() + timedelta(days=grant_days)

        db.add(t)
        db.flush()

        phone_n = normalize_phone(owner_phone)
        exists = db.query(AuthUser).filter(AuthUser.phone == phone_n).first()
        if exists:
            db.rollback()
            return RedirectResponse(
                url="/superadmin?error=phone_exists", status_code=303
            )

        salt, pw_hash = hash_password(owner_password)
        u = AuthUser(
            tenant_id=t.id,
            phone=phone_n,
            name=owner_name.strip() or "Owner",
            role="owner",
            password_salt=salt,
            password_hash=pw_hash,
            is_active=True,
        )
        db.add(u)
        db.commit()

        return RedirectResponse(url="/superadmin", status_code=303)
    finally:
        db.close()


@router.post("/tenants/{tenant_id}/grant")
def sa_grant_days(
    request: Request,
    tenant_id: int,
    days: int = Form(...),
):
    redir = _require_auth(request)
    if redir:
        return redir

    db = SessionLocal()
    try:
        t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not t:
            return RedirectResponse(url="/superadmin", status_code=303)

        base = (
            t.access_until
            if (t.access_until and t.access_until > datetime.utcnow())
            else datetime.utcnow()
        )
        t.access_until = base + timedelta(days=int(days))
        db.commit()
        return RedirectResponse(url="/superadmin", status_code=303)
    finally:
        db.close()


@router.post("/tenants/{tenant_id}/toggle")
def sa_toggle(
    request: Request,
    tenant_id: int,
    is_active: int = Form(...),
):
    redir = _require_auth(request)
    if redir:
        return redir

    db = SessionLocal()
    try:
        t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if t:
            t.is_active = bool(int(is_active))
            db.commit()
        return RedirectResponse(url="/superadmin", status_code=303)
    finally:
        db.close()


@router.post("/tenants/{tenant_id}/impersonate")
def sa_impersonate(
    request: Request,
    tenant_id: int,
):
    """Войти как owner нужного tenant-а (импersonация)."""
    redir = _require_auth(request)
    if redir:
        return redir

    db = SessionLocal()
    try:
        owner = db.scalar(
            select(AuthUser).where(
                AuthUser.tenant_id == tenant_id,
                AuthUser.role == "owner",
                AuthUser.is_active == True,
            )
        )
        if not owner:
            return RedirectResponse(url="/superadmin?error=no_owner", status_code=303)

        # Сохраняем флаг суперадмин для возврата
        request.session["_sa_impersonating"] = True
        request.session["_sa_prev_session"] = {
            "uid": request.session.get("uid"),
            "phone": request.session.get("phone"),
            "name": request.session.get("name"),
            "role": request.session.get("role"),
            "tenant_id": request.session.get("tenant_id"),
        }

        # Входим как owner
        request.session["uid"] = owner.id
        request.session["phone"] = owner.phone
        request.session["name"] = owner.name or owner.phone
        request.session["role"] = owner.role
        request.session["tenant_id"] = owner.tenant_id

        return RedirectResponse(url="/admin", status_code=303)
    finally:
        db.close()


@router.get("/exit-impersonate")
def sa_exit_impersonate(request: Request):
    """Вернуться из импersonации в суперадмин."""
    if request.session.get("_sa_impersonating"):
        prev = request.session.pop("_sa_prev_session", {})
        request.session.pop("_sa_impersonating", None)
        # Восстанавливаем оригинальную сессию (или очищаем)
        for k in ("uid", "phone", "name", "role", "tenant_id"):
            if prev.get(k):
                request.session[k] = prev[k]
            else:
                request.session.pop(k, None)

    return RedirectResponse(url="/superadmin", status_code=303)