# app/api/wa_official_api.py
"""
Официальный WhatsApp: статус канала, шаблоны, баланс кредитов (для owner/admin)
и публичный вебхук статусов доставки.

/api/whatsapp/official/*  — закрыто ролью owner/admin (ADMIN_PLUS_PATHS в main.py)
/wa-webhook/{secret}      — публичный, секрет в URL (исключение в AuthGuardMiddleware)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_utils import must_tenant_id, must_network_id, require_role
from app.models.broadcast import Broadcast, WaMessage
from app.models.wa_official import WaOfficialChannel
from app.services import wa_credits
from app.services.wa_official import channel_public, get_channel, list_templates, parse_statuses

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp/official", tags=["wa-official"])
webhook_router = APIRouter(tags=["wa-official-webhook"])

ROLES = ("owner", "admin")


@router.get("/status")
def official_status(request: Request, db: Session = Depends(get_db)):
    require_role(request, *ROLES)
    tenant_id = must_tenant_id(request)
    network_id = must_network_id(request)
    ch = get_channel(db, tenant_id, network_id)
    return {
        "channel": channel_public(ch),
        "credits": wa_credits.get_balance(db, network_id),
    }


@router.get("/templates")
def official_templates(request: Request, db: Session = Depends(get_db)):
    require_role(request, *ROLES)
    ch = get_channel(db, must_tenant_id(request), must_network_id(request))
    res = list_templates(ch, approved_only=True)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "Не удалось получить шаблоны")
    return res


@router.get("/credits")
def official_credits(request: Request, db: Session = Depends(get_db)):
    require_role(request, *ROLES)
    network_id = must_network_id(request)
    return {
        "balance": wa_credits.get_balance(db, network_id),
        "ledger": wa_credits.ledger(db, network_id, limit=100),
    }


# ─────────────────────────────────────────────────────────────
# Вебхук статусов доставки
# ─────────────────────────────────────────────────────────────
@webhook_router.get("/wa-webhook/{secret}")
def webhook_verify(secret: str, request: Request, db: Session = Depends(get_db)):
    """Проверка вебхука Meta (hub.challenge). verify_token = тот же секрет."""
    ch = db.query(WaOfficialChannel).filter(WaOfficialChannel.webhook_secret == secret).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Not found")
    qp = request.query_params
    if qp.get("hub.mode") == "subscribe" and qp.get("hub.verify_token") == secret:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(qp.get("hub.challenge") or "")
    return {"ok": True}


@webhook_router.post("/wa-webhook/{secret}")
async def webhook_receive(secret: str, request: Request, db: Session = Depends(get_db)):
    ch = db.query(WaOfficialChannel).filter(WaOfficialChannel.webhook_secret == secret).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    for st in parse_statuses(payload):
        mid = st.get("id")
        if not mid:
            continue
        msg = db.query(WaMessage).filter(WaMessage.provider_message_id == mid).first()
        if msg is None:
            continue
        status = st.get("status")
        if status == "failed" and msg.status != "failed":
            # Meta не доставила и не берёт деньги — возвращаем кредит компании
            was_sent = msg.status == "sent"
            msg.status = "failed"
            msg.error = (st.get("error") or "failed")[:490]
            if int(msg.credits_charged or 0) > 0:
                network_id = None
                b = db.get(Broadcast, msg.broadcast_id) if msg.broadcast_id else None
                if b is not None:
                    network_id = b.network_id
                    if was_sent:
                        b.sent = max(0, int(b.sent or 0) - 1)
                    b.failed = int(b.failed or 0) + 1
                else:
                    from app.services.loyalty_engine import resolve_network_id
                    network_id = resolve_network_id(db, msg.tenant_id)
                if network_id:
                    wa_credits.refund(db, network_id, int(msg.credits_charged), broadcast_id=msg.broadcast_id)
                msg.credits_charged = 0
        elif status in ("delivered", "read") and msg.status == "sending":
            msg.status = "sent"
    db.commit()
    return {"ok": True}
