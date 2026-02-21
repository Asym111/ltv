# app/web/admin_campaigns.py
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory='templates')


def render(request: Request, tpl: str, **ctx):
    current_user = getattr(request.state, 'user', None)
    return templates.TemplateResponse(tpl, {'request': request, 'current_user': current_user, **ctx})


@router.get('/admin/campaigns', response_class=HTMLResponse)
@router.get('/admin/campaigns/', response_class=HTMLResponse, include_in_schema=False)
def admin_campaigns(request: Request):
    return render(
        request,
        'admin/campaigns.html',
        current_page='campaigns',
        page_title='Рекламные кампании',
        page_subtitle='Создавайте кампании по сегментам и собирайте аудиторию',
    )


@router.get('/admin/campaigns/{campaign_id}', response_class=HTMLResponse)
@router.get('/admin/campaigns/{campaign_id}/', response_class=HTMLResponse, include_in_schema=False)
def admin_campaign_detail(request: Request, campaign_id: int):
    return render(
        request,
        'admin/campaign_detail.html',
        current_page='campaigns',
        page_title=f'Рекламная кампания #{campaign_id}',
        page_subtitle='Получатели, статус и запуск рассылки',
        campaign_id=campaign_id,
    )