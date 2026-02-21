# app/api/whatsapp.py
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.whatsapp import (
    get_status,
    send_message,
    send_campaign_messages,
    render_template,
)
from app.services.campaigns import get_campaign
from app.models.campaign import CampaignRecipient

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# ── Schemas ────────────────────────────────────────────────────
class SendOneIn(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20)
    message: str = Field(..., min_length=1, max_length=4096)


class SendCampaignIn(BaseModel):
    campaign_id: int
    template: str = Field(..., min_length=1, max_length=4096)
    dry_run: bool = False


class TemplatePreviewIn(BaseModel):
    template: str
    sample: dict = {}


# ── Auth helper ───────────────────────────────────────────────
def require_admin(request: Request):
    u = getattr(request.state, "user", None) or {}
    if u.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin")
    return u


# ── Endpoints ──────────────────────────────────────────────────

@router.get("/status")
def whatsapp_status():
    """Статус подключения GreenAPI инстанса."""
    return get_status()


@router.post("/send")
def whatsapp_send_one(
    payload: SendOneIn,
    request: Request,
):
    """Отправить сообщение одному клиенту."""
    require_admin(request)
    result = send_message(payload.phone, payload.message)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Ошибка отправки"))
    return result


@router.post("/send-campaign")
def whatsapp_send_campaign(
    payload: SendCampaignIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Массовая рассылка по кампании."""
    require_admin(request)

    campaign = get_campaign(db, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Кампания не найдена")

    # Получаем получателей кампании
    rows = (
        db.query(CampaignRecipient)
        .filter(CampaignRecipient.campaign_id == payload.campaign_id)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=400, detail="Кампания не имеет получателей. Сначала сформируйте список.")

    recipients = [
        {
            "phone":          r.phone,
            "name":           r.full_name or "Клиент",
            "bonus":          campaign.suggested_bonus or 0,
            "campaign_name":  campaign.name or "",
        }
        for r in rows
    ]

    result = send_campaign_messages(
        recipients=recipients,
        template=payload.template,
        dry_run=payload.dry_run,
    )

    return {
        "campaign_id":   payload.campaign_id,
        "campaign_name": campaign.name,
        "dry_run":       payload.dry_run,
        **result,
    }


@router.post("/preview-template")
def whatsapp_preview_template(payload: TemplatePreviewIn):
    """Предпросмотр шаблона с тестовыми данными."""
    sample = {
        "name":  "Айгуль",
        "phone": "77001234567",
        "bonus": "3000",
        **payload.sample,
    }
    return {"preview": render_template(payload.template, sample)}


@router.get("/templates")
def whatsapp_templates():
    """Встроенные шаблоны сообщений."""
    return {"templates": BUILTIN_TEMPLATES}


# ── Built-in templates ─────────────────────────────────────────
BUILTIN_TEMPLATES = [
    {
        "key":   "welcome",
        "title": "Приветственный бонус",
        "text":  "Привет, {name}! 🎉 Добро пожаловать в нашу программу лояльности. Вам начислено {bonus} бонусов. Используйте их при следующей покупке!",
    },
    {
        "key":   "winback",
        "title": "Возврат клиента",
        "text":  "Привет, {name}! Мы скучаем по вам 💛 Специально для вас — {bonus} бонусов. Приходите, будем рады видеть вас снова!",
    },
    {
        "key":   "vip",
        "title": "VIP оффер",
        "text":  "Уважаемый(ая) {name}, как наш VIP-клиент вы получаете эксклюзивное предложение: {bonus} бонусов на ваш следующий визит! ⭐",
    },
    {
        "key":   "birthday",
        "title": "День рождения",
        "text":  "С Днём рождения, {name}! 🎂 В честь вашего праздника мы начислили вам {bonus} бонусов. Желаем здоровья и счастья!",
    },
    {
        "key":   "reminder",
        "title": "Напоминание о бонусах",
        "text":  "Привет, {name}! Напоминаем — у вас есть {bonus} бонусов, которые скоро сгорят. Используйте их при следующей покупке!",
    },
    {
        "key":   "custom",
        "title": "Свой текст",
        "text":  "Привет, {name}! {bonus}",
    },
]