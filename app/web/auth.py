# app/web/auth.py
from __future__ import annotations

import os
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import TemplateNotFound

from app.core.database import SessionLocal
from app.core.security import normalize_phone, verify_password
from app.models.auth import AuthUser, Tenant
from app.models.auth import Tenant as TenantModel

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _pick_login_template() -> str:
    try:
        templates.env.get_template("auth/login.html")
        return "auth/login.html"
    except TemplateNotFound:
        return "admin/auth/login.html"


def render_login(request: Request, *, error: str | None, info: str | None, next_url: str):
    remember_days = int(os.getenv("AUTH_REMEMBER_DAYS", "30") or "30")
    tpl = _pick_login_template()
    return templates.TemplateResponse(
        tpl,
        {
            "request": request,
            "error": error,
            "info": info,
            "next_url": next_url,
            "remember_days": remember_days,
        },
    )


@router.get("/auth", response_class=HTMLResponse)
@router.get("/auth/", response_class=HTMLResponse, include_in_schema=False)
def login_get(
    request: Request,
    next: str | None = None,
    e: str | None = None,
    i: str | None = None,
):
    # Уже залогинен → редирект
    if request.session.get("uid"):
        return RedirectResponse(url=next or "/admin", status_code=302)

    next_url = next or "/admin"
    error = None
    info = i

    if e == "expired":
        error = "Доступ к аккаунту истёк. Продлите подписку и войдите снова."
    elif e == "disabled":
        error = "Аккаунт отключён. Обратитесь к администратору."

    return render_login(request, error=error, info=info, next_url=next_url)


@router.post("/auth")
@router.post("/auth/", include_in_schema=False)
def login_post(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    next: str = Form("/admin"),
):
    db = SessionLocal()
    try:
        phone_n = normalize_phone(phone)

        user: AuthUser | None = (
            db.query(AuthUser)
            .filter(AuthUser.phone == phone_n)
            .first()
        )

        if not user or not user.is_active:
            return render_login(
                request,
                error="Неверный логин или пароль.",
                info=None,
                next_url=next,
            )

        tenant: Tenant | None = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if not tenant or not tenant.is_active:
            return render_login(
                request,
                error="Аккаунт отключён. Обратитесь к администратору.",
                info=None,
                next_url=next,
            )

        # Корень сети: филиал живёт на подписке головного тенанта
        root: Tenant | None = tenant
        if tenant.parent_tenant_id:
            root = db.query(Tenant).filter(Tenant.id == tenant.parent_tenant_id).first()
            if not root or not root.is_active:
                return render_login(
                    request,
                    error="Аккаунт сети отключён. Обратитесь к администратору.",
                    info=None,
                    next_url=next,
                )

        access_until = getattr(root, "access_until", None)
        if access_until is not None and access_until < datetime.utcnow():
            return render_login(
                request,
                error="Доступ к аккаунту истёк. Продлите подписку и попробуйте снова.",
                info=None,
                next_url=next,
            )

        if not verify_password(password, user.password_salt, user.password_hash):
            return render_login(
                request,
                error="Неверный логин или пароль.",
                info=None,
                next_url=next,
            )

        # ✅ Записываем время последнего входа
        user.last_login_at = datetime.utcnow()
        db.commit()

        # ✅ Сохраняем сессию + CSRF токен + session_version
        request.session.clear()
        request.session["uid"]              = user.id
        request.session["phone"]            = user.phone
        request.session["name"]             = user.name
        request.session["role"]             = user.role
        request.session["tenant_id"]        = user.tenant_id
        # Мультифилиальность: домашний тенант, активный контекст и корень сети
        request.session["home_tenant_id"]   = user.tenant_id
        request.session["active_tenant_id"] = user.tenant_id
        request.session["network_id"]       = root.id if root else user.tenant_id
        request.session["csrf_token"]       = secrets.token_hex(32)
        request.session["session_version"]  = user.session_version
        request.session["tenant_name"] = tenant.name if tenant else ""

        # Безопасный редирект — только внутренние пути
        safe_next = next if (next and next.startswith("/") and not next.startswith("//")) else "/admin"
        return RedirectResponse(url=safe_next, status_code=303)

    finally:
        db.close()


@router.get("/logout")
@router.get("/logout/", include_in_schema=False)
def logout(request: Request, next: str | None = None):
    request.session.clear()
    return RedirectResponse(
        url=f"/auth?next={quote(next or '/admin')}&i=Вы+вышли+из+системы",
        status_code=303,
    )


# ── Logout со всех устройств ──────────────────────────────────
@router.post("/logout-all")
@router.post("/logout-all/", include_in_schema=False)
def logout_all(request: Request):
    """Сбрасывает все сессии пользователя."""
    uid = request.session.get("uid")
    if not uid:
        return RedirectResponse(url="/auth?e=disabled", status_code=303)

    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.id == int(uid)).first()
        if user:
            user.session_version = (user.session_version or 0) + 1
            db.commit()
    finally:
        db.close()

    request.session.clear()
    return RedirectResponse(
        url="/auth?i=Вы+вышли+из+всех+устройств",
        status_code=303,
    )
