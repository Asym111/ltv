# app/web/admin.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def render(request: Request, tpl: str, **ctx):
    return templates.TemplateResponse(tpl, {"request": request, **ctx})


# ✅ Главная админки = Рабочий стол
@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/", response_class=HTMLResponse, include_in_schema=False)
def admin_desktop(request: Request):
    return render(
        request,
        "admin/desktop.html",
        current_page="desktop",
        page_title="Рабочий стол",
        page_subtitle="Главная панель управления",
    )


# ✅ Новости отдельной страницей (бывшая главная)
@router.get("/admin/news", response_class=HTMLResponse)
@router.get("/admin/news/", response_class=HTMLResponse, include_in_schema=False)
def admin_news(request: Request):
    return render(
        request,
        "admin/news.html",
        current_page="news",
        page_title="Новости",
        page_subtitle="Лента событий и уведомлений",
    )


# Клиенты
@router.get("/admin/clients", response_class=HTMLResponse)
@router.get("/admin/clients/", response_class=HTMLResponse, include_in_schema=False)
def admin_clients(request: Request):
    return render(
        request,
        "admin/clients_db.html",
        current_page="clients",
        page_title="Клиенты",
        page_subtitle="Список клиентов и быстрый переход в карточку",
    )


# Карточка клиента
@router.get("/admin/client/{phone}", response_class=HTMLResponse)
@router.get("/admin/client/{phone}/", response_class=HTMLResponse, include_in_schema=False)
def admin_client_card(request: Request, phone: str):
    return render(
        request,
        "admin/client.html",
        current_page="clients",
        page_title="Карточка клиента",
        page_subtitle=f"Телефон: {phone}",
        phone=phone,
    )


# Транзакции
@router.get("/admin/transactions", response_class=HTMLResponse)
@router.get("/admin/transactions/", response_class=HTMLResponse, include_in_schema=False)
def admin_transactions(request: Request):
    return render(
        request,
        "admin/transactions.html",
        current_page="transactions",
        page_title="Транзакции",
        page_subtitle="Поиск, список и проведение новых транзакций",
    )


# Настройки
@router.get("/admin/settings", response_class=HTMLResponse)
@router.get("/admin/settings/", response_class=HTMLResponse, include_in_schema=False)
def admin_settings(request: Request):
    return render(
        request,
        "admin/settings.html",
        current_page="settings",
        page_title="Настройки",
        page_subtitle="Правила начисления, списания, активации и дня рождения",
    )


# База клиентов (временно)
@router.get("/admin/clients-db", response_class=HTMLResponse)
@router.get("/admin/clients-db/", response_class=HTMLResponse, include_in_schema=False)
def admin_clients_db(request: Request):
    return render(
        request,
        "admin/clients_db.html",
        current_page="clients_db",
        page_title="База клиентов",
        page_subtitle="Справочник клиентов (временно общий экран со списком клиентов)",
    )


@router.get("/admin/whatsapp", response_class=HTMLResponse)
@router.get("/admin/whatsapp/", response_class=HTMLResponse, include_in_schema=False)
def admin_whatsapp(request: Request):
    return render(
        request,
        "admin/placeholder.html",
        current_page="whatsapp",
        page_title="WhatsApp",
        page_subtitle="Модуль в разработке",
    )


# ✅ Аналитика
@router.get("/admin/analytics", response_class=HTMLResponse)
@router.get("/admin/analytics/", response_class=HTMLResponse, include_in_schema=False)
def admin_analytics(request: Request):
    return render(
        request,
        "admin/analytics.html",
        current_page="analytics",
        page_title="Аналитика",
        page_subtitle="Срезы 7/30/90 дней и сегменты (RFM базово)",
    )


# ✅ Список клиентов сегмента
@router.get("/admin/analytics/segment/{key}", response_class=HTMLResponse)
@router.get("/admin/analytics/segment/{key}/", response_class=HTMLResponse, include_in_schema=False)
def admin_analytics_segment(request: Request, key: str):
    titles = {
        "new": "Новые",
        "active": "Активные",
        "sleeping": "Спящие",
        "risk": "В зоне риска",
        "lost": "Потерянные",
        "vip": "VIP",
    }
    title = titles.get(key, key)

    return render(
        request,
        "admin/analytics_segment.html",
        current_page="analytics",
        page_title=f"Сегмент: {title}",
        page_subtitle="Список клиентов сегмента и переход в карточку",
        segment_key=key,
        segment_title=title,
    )
