# app/web/admin_accounts.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.core.database import SessionLocal
from app.models.auth import Tenant

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def render(request: Request, tpl: str, **ctx):
    current_user = getattr(request.state, "user", None)
    return templates.TemplateResponse(
        tpl, {"request": request, "current_user": current_user, **ctx}
    )


@router.get("/admin/accounts", response_class=HTMLResponse)
@router.get("/admin/accounts/", response_class=HTMLResponse, include_in_schema=False)
def admin_accounts(request: Request):
    current_user = getattr(request.state, "user", None) or {}
    tenant_name = ""
    tenant_access = None

    tid = current_user.get("tenant_id")
    if tid:
        db = SessionLocal()
        try:
            t = db.query(Tenant).filter(Tenant.id == tid).first()
            if t:
                tenant_name = t.name or ""
                tenant_access = t.access_until
        finally:
            db.close()

    return render(
        request,
        "admin/accounts.html",
        current_page="accounts",
        page_title="Аккаунт",
        page_subtitle="Управление командой, доступами и профилем компании",
        tenant_name=tenant_name,
        tenant_access=tenant_access,
    )