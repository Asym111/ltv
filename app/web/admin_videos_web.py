# app/web/admin_videos.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/admin/videos", response_class=HTMLResponse)
@router.get("/admin/videos/", response_class=HTMLResponse, include_in_schema=False)
def admin_videos(request: Request):
    current_user = getattr(request.state, "user", None)
    return templates.TemplateResponse("admin/videos.html", {
        "request": request,
        "current_user": current_user,
        "current_page": "videos",
        "page_title": "База знаний",
        "page_subtitle": "Обучающие видео и полезные материалы",
    })