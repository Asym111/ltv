# app/web/admin_campaigns.py
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

router = APIRouter(tags=["admin_pages"])


@router.get("/admin/campaigns", response_class=HTMLResponse)
def admin_campaigns(request: Request):
    return templates.TemplateResponse("admin/campaigns.html", {"request": request})


@router.get("/admin/campaigns/{campaign_id}", response_class=HTMLResponse)
def admin_campaign_detail(request: Request, campaign_id: int):
    return templates.TemplateResponse(
        "admin/campaign_detail.html",
        {"request": request, "campaign_id": campaign_id},
    )
