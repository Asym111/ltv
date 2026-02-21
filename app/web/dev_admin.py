# app/web/dev_admin.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from app.core.database import SessionLocal
from app.core.security import normalize_phone, hash_password
from app.models.auth import Tenant, AuthUser

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def check_dev_token(token: str | None) -> bool:
    expected = os.getenv("DEV_ADMIN_TOKEN", "").strip()
    return bool(expected) and bool(token) and token == expected


@router.get("/dev/tenants", response_class=HTMLResponse)
def dev_tenants(request: Request, token: str | None = None):
    if not check_dev_token(token):
        return PlainTextResponse("Forbidden", status_code=403)

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).order_by(Tenant.id.desc()).all()
        users = db.query(AuthUser).all()
        users_by_tenant = {}
        for u in users:
            users_by_tenant.setdefault(u.tenant_id, 0)
            users_by_tenant[u.tenant_id] += 1

        return templates.TemplateResponse(
            "dev/tenants.html",
            {
                "request": request,
                "token": token,
                "tenants": tenants,
                "users_by_tenant": users_by_tenant,
                "now": datetime.utcnow(),
            },
        )
    finally:
        db.close()


@router.post("/dev/tenants/create")
def dev_create_tenant(
    request: Request,
    token: str = Form(...),
    name: str = Form(...),
    owner_phone: str = Form(...),
    owner_password: str = Form(...),
    owner_name: str = Form("Owner"),
    grant_days: int = Form(0),
):
    if not check_dev_token(token):
        return PlainTextResponse("Forbidden", status_code=403)

    db = SessionLocal()
    try:
        t = Tenant(name=name.strip() or "Account", is_active=True, access_until=None)
        if grant_days and grant_days > 0:
            t.access_until = datetime.utcnow() + timedelta(days=int(grant_days))

        db.add(t)
        db.flush()

        phone_n = normalize_phone(owner_phone)
        # phone у auth_users уникальный глобально
        exists = db.query(AuthUser).filter(AuthUser.phone == phone_n).first()
        if exists:
            return PlainTextResponse("Owner phone already exists in auth_users", status_code=400)

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

        return RedirectResponse(url=f"/dev/tenants?token={token}", status_code=303)
    finally:
        db.close()


@router.post("/dev/tenants/{tenant_id}/grant")
def dev_grant_days(
    tenant_id: int,
    token: str = Form(...),
    days: int = Form(...),
):
    if not check_dev_token(token):
        return PlainTextResponse("Forbidden", status_code=403)

    db = SessionLocal()
    try:
        t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not t:
            return PlainTextResponse("Tenant not found", status_code=404)

        d = int(days)
        base = t.access_until if (t.access_until and t.access_until > datetime.utcnow()) else datetime.utcnow()
        t.access_until = base + timedelta(days=d)
        db.commit()

        return RedirectResponse(url=f"/dev/tenants?token={token}", status_code=303)
    finally:
        db.close()


@router.post("/dev/tenants/{tenant_id}/toggle")
def dev_toggle_active(
    tenant_id: int,
    token: str = Form(...),
    is_active: int = Form(...),  # 1/0
):
    if not check_dev_token(token):
        return PlainTextResponse("Forbidden", status_code=403)

    db = SessionLocal()
    try:
        t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not t:
            return PlainTextResponse("Tenant not found", status_code=404)

        t.is_active = bool(int(is_active))
        db.commit()

        return RedirectResponse(url=f"/dev/tenants?token={token}", status_code=303)
    finally:
        db.close()
