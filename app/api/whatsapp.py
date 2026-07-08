# app/api/whatsapp.py
from __future__ import annotations

import hashlib
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decrypt_field
from app.core.tenant_utils import must_network_id
from app.models.user import User
from app.models.broadcast import Broadcast, WaTemplate
from app.services.whatsapp import (
    get_status,
    get_qr,
    logout,
    send_message,
    send_campaign_messages,
    render_template,
    normalize_phone,
)
from app.services.broadcast_worker import log_wa_message
from app.services.campaigns import get_campaign
from app.models.campaign import CampaignRecipient

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


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


class TemplateCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    text: str = Field(..., min_length=1, max_length=4096)


def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


def require_role(request: Request, *allowed: str):
    u = getattr(request.state, "user", None) or {}
    role = u.get("role", "")
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Access denied. Required roles: {allowed}")
    return u


@router.get("/status")
def whatsapp_status(request: Request):
    require_role(request, "owner", "admin", "manager")
    tenant_id = must_tenant_id(request)
    return get_status(tenant_id=str(tenant_id))


@router.get("/qr")
def whatsapp_qr(request: Request):
    require_role(request, "owner", "admin")
    tenant_id = must_tenant_id(request)
    return get_qr(tenant_id=str(tenant_id))


@router.post("/logout")
def whatsapp_logout(request: Request):
    require_role(request, "owner", "admin")
    tenant_id = must_tenant_id(request)
    return logout(tenant_id=str(tenant_id))


@router.post("/send")
def whatsapp_send_one(payload: SendOneIn, request: Request, db: Session = Depends(get_db)):
    require_role(request, "owner", "admin", "manager")
    tenant_id = must_tenant_id(request)
    result = send_message(payload.phone, payload.message, tenant_id=str(tenant_id))

    # Журнал: одиночное сообщение (+ привязка к клиенту сети, если найден)
    user_id = None
    display_name = None
    try:
        network_id = must_network_id(request)
        p = normalize_phone(payload.phone)
        p_hash = hashlib.sha256(p.encode()).hexdigest()
        u = db.query(User).filter(User.tenant_id == network_id, User.phone_hash == p_hash).first()
        if u:
            user_id = u.id
            display_name = (decrypt_field(u.full_name) or "").strip() if u.full_name else None
    except Exception:
        pass
    log_wa_message(
        db,
        tenant_id=tenant_id,
        phone=normalize_phone(payload.phone),
        kind="single",
        status="sent" if result.get("ok") else "failed",
        text=payload.message,
        user_id=user_id,
        display_name=display_name,
        error=result.get("error"),
    )

    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Ошибка отправки"))
    return result


@router.post("/send-campaign")
def whatsapp_send_campaign(
    payload: SendCampaignIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Совместимость со старым флоу кампаний: теперь вместо мгновенного
    синхронного цикла создаётся БЕЗОПАСНАЯ фоновая рассылка (Broadcast)
    с задержками, лимитами и журналом.
    """
    require_role(request, "owner", "admin")
    tenant_id = must_tenant_id(request)
    network_id = must_network_id(request)

    campaign = get_campaign(db, payload.campaign_id, tenant_id=tenant_id)
    if not campaign:
        # кампания могла быть создана в другом контексте сети
        campaign = get_campaign(db, payload.campaign_id)
        if not campaign or campaign.tenant_id not in (tenant_id, network_id):
            raise HTTPException(status_code=404, detail="Кампания не найдена")

    rows = (
        db.query(CampaignRecipient)
        .filter(CampaignRecipient.campaign_id == payload.campaign_id)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=400, detail="Кампания не имеет получателей. Сначала нажмите «Собрать список».")

    if payload.dry_run:
        recipients = [
            {
                "phone":         r.phone,
                "name":          r.full_name or "Клиент",
                "bonus":         campaign.suggested_bonus or 0,
                "campaign_name": campaign.name or "",
            }
            for r in rows
        ]
        result = send_campaign_messages(
            recipients=recipients,
            template=payload.template,
            dry_run=True,
            tenant_id=str(tenant_id),
        )
        return {"campaign_id": payload.campaign_id, "campaign_name": campaign.name, "dry_run": True, **result}

    from app.api.broadcasts import start_broadcast_core

    u = getattr(request.state, "user", None) or {}
    b = Broadcast(
        tenant_id=tenant_id,
        network_id=network_id,
        name=f"Кампания: {campaign.name}",
        message_template=payload.template,
        audience_kind="campaign",
        audience_json={"campaign_id": campaign.id},
        exclude_recent_days=0,  # кампания — осознанно собранный список
        status="draft",
        created_by=u.get("id"),
    )
    db.add(b)
    db.commit()
    db.refresh(b)

    result = start_broadcast_core(db, b)
    campaign.status = "sent"
    db.commit()
    return {
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "dry_run": False,
        "broadcast_id": b.id,
        "queued": result.get("queued", 0),
        "message": "Рассылка запущена в фоне с безопасными задержками. Прогресс — в разделе WhatsApp → История.",
    }


@router.post("/preview-template")
def whatsapp_preview_template(payload: TemplatePreviewIn, request: Request):
    require_role(request, "owner", "admin", "manager")
    sample = {"name": "Айгуль", "phone": "77001234567", "bonus": "3000", **payload.sample}
    return {"preview": render_template(payload.template, sample)}


@router.get("/templates")
def whatsapp_templates(request: Request, db: Session = Depends(get_db)):
    """Встроенные шаблоны + сохранённые шаблоны сети."""
    require_role(request, "owner", "admin", "manager", "cashier")
    network_id = must_network_id(request)

    custom = (
        db.query(WaTemplate)
        .filter(WaTemplate.tenant_id == network_id)
        .order_by(WaTemplate.id.desc())
        .all()
    )
    return {
        "templates": [
            *[
                {"id": t.id, "key": f"custom_{t.id}", "title": t.title, "text": t.text, "custom": True}
                for t in custom
            ],
            *[{**t, "custom": False} for t in BUILTIN_TEMPLATES],
        ]
    }


@router.post("/templates")
def whatsapp_template_create(payload: TemplateCreateIn, request: Request, db: Session = Depends(get_db)):
    require_role(request, "owner", "admin")
    network_id = must_network_id(request)
    t = WaTemplate(tenant_id=network_id, title=payload.title.strip(), text=payload.text)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "key": f"custom_{t.id}", "title": t.title, "text": t.text, "custom": True}


@router.delete("/templates/{template_id}")
def whatsapp_template_delete(template_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, "owner", "admin")
    network_id = must_network_id(request)
    t = db.query(WaTemplate).filter(
        WaTemplate.id == template_id,
        WaTemplate.tenant_id == network_id,
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    db.delete(t)
    db.commit()
    return {"ok": True}


BUILTIN_TEMPLATES = [
    {"key": "welcome", "title": "Приветственный бонус",  "text": "Привет, {name}! 🎉 Добро пожаловать в нашу программу лояльности. Вам начислено {bonus} бонусов. Используйте их при следующей покупке!"},
    {"key": "winback",  "title": "Возврат клиента",       "text": "Привет, {name}! Мы скучаем по вам 💛 Специально для вас — {bonus} бонусов. Приходите, будем рады видеть вас снова!"},
    {"key": "vip",      "title": "VIP оффер",             "text": "Уважаемый(ая) {name}, как наш VIP-клиент вы получаете эксклюзивное предложение: {bonus} бонусов на ваш следующий визит! ⭐"},
    {"key": "birthday", "title": "День рождения",         "text": "С Днём рождения, {name}! 🎂 В честь вашего праздника мы начислили вам {bonus} бонусов. Желаем здоровья и счастья!"},
    {"key": "reminder", "title": "Напоминание о бонусах", "text": "Привет, {name}! Напоминаем — у вас есть {bonus} бонусов, которые скоро сгорят. Используйте их при следующей покупке!"},
    {"key": "custom",   "title": "Свой текст",            "text": "Привет, {name}! {bonus}"},
]
