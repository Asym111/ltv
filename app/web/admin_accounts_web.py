# app/web/admin_accounts.py
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

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
    return render(
        request,
        "admin/accounts.html",
        current_page="accounts",
        page_title="Аккаунт",
        page_subtitle="Управление командой, доступами и профилем компании",
    )