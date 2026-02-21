# app/web/admin_whatsapp.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/admin/whatsapp", response_class=HTMLResponse)
def admin_whatsapp(request: Request):
    current_user = getattr(request.state, "user", None)
    return templates.TemplateResponse("admin/whatsapp.html", {
        "request":      request,
        "current_user": current_user,
        "current_page": "whatsapp",
        "page_title":   "WhatsApp",
        "page_subtitle": "Рассылки и сообщения клиентам через GreenAPI",
    })