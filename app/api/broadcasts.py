# app/api/broadcasts.py
"""
API центра WhatsApp-рассылок.

Роутер монтируется под /api/whatsapp/broadcasts — путь /api/whatsapp уже
закрыт ролью owner/admin в AuthGuardMiddleware (main.py, ADMIN_PLUS_PATHS).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_utils import must_tenant_id, must_network_id, network_tenant_ids, require_role
from app.models.broadcast import Broadcast, WaMessage
from app.services.broadcast_audience import build_audience, estimate_audience, AUDIENCE_KINDS
from app.services.broadcast_worker import (
    render_message,
    start_broadcast_worker,
    log_wa_message,
    _in_send_window,
    _sent_today_count,
)
from app.services.whatsapp import get_status, send_message, normalize_phone

router = APIRouter(prefix="/whatsapp/broadcasts", tags=["broadcasts"])

BROADCAST_ROLES = ("owner", "admin")

# Пресеты скорости отправки
SPEED_PRESETS = {
    "safe":     {"delay_min_sec": 7,  "delay_max_sec": 14, "batch_size": 25, "batch_pause_sec": 90},
    "slow":     {"delay_min_sec": 12, "delay_max_sec": 20, "batch_size": 20, "batch_pause_sec": 120},
    "fast":     {"delay_min_sec": 4,  "delay_max_sec": 8,  "batch_size": 30, "batch_pause_sec": 60},
}


# ── Schemas ──────────────────────────────────────────────────

class AudienceIn(BaseModel):
    audience_kind: str = Field(default="all")
    audience_params: Dict[str, Any] = Field(default_factory=dict)
    exclude_recent_days: int = Field(default=7, ge=0, le=90)


class BroadcastCreateIn(AudienceIn):
    name: Optional[str] = Field(default=None, max_length=200)
    message_template: str = Field(..., min_length=1, max_length=4096)
    speed: str = Field(default="safe")
    daily_cap: int = Field(default=250, ge=10, le=1000)


class TestSendIn(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20)
    message_template: str = Field(..., min_length=1, max_length=4096)


# ── Helpers ──────────────────────────────────────────────────

def _eta_seconds(b: Broadcast, remaining: int) -> int:
    if remaining <= 0:
        return 0
    avg_delay = (int(b.delay_min_sec or 7) + int(b.delay_max_sec or 14)) / 2
    per_msg_batch = (int(b.batch_pause_sec or 90) / max(1, int(b.batch_size or 25)))
    return int(remaining * (avg_delay + per_msg_batch))


def _broadcast_out(b: Broadcast, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    remaining = max(0, int(b.total or 0) - int(b.sent or 0) - int(b.failed or 0) - int(b.skipped or 0))
    out = {
        "id": b.id,
        "name": b.name,
        "status": b.status,
        "audience_kind": b.audience_kind,
        "audience_params": b.audience_json or {},
        "message_template": b.message_template,
        "total": int(b.total or 0),
        "sent": int(b.sent or 0),
        "failed": int(b.failed or 0),
        "skipped": int(b.skipped or 0),
        "remaining": remaining,
        "eta_seconds": _eta_seconds(b, remaining) if b.status == "running" else 0,
        "delay_min_sec": b.delay_min_sec,
        "delay_max_sec": b.delay_max_sec,
        "daily_cap": b.daily_cap,
        "exclude_recent_days": b.exclude_recent_days,
        "last_error": b.last_error,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "finished_at": b.finished_at.isoformat() if b.finished_at else None,
    }
    if extra:
        out.update(extra)
    return out


def _get_own_broadcast(db: Session, broadcast_id: int, network_id: int) -> Broadcast:
    b = db.query(Broadcast).filter(
        Broadcast.id == broadcast_id,
        Broadcast.network_id == network_id,
    ).first()
    if not b:
        raise HTTPException(status_code=404, detail="Рассылка не найдена")
    return b


# ── Endpoints ────────────────────────────────────────────────

@router.post("/preview")
def preview_audience(payload: AudienceIn, request: Request, db: Session = Depends(get_db)):
    """Живой счётчик получателей + предупреждения перед запуском."""
    require_role(request, *BROADCAST_ROLES)
    tenant_id = must_tenant_id(request)
    network_id = must_network_id(request)
    tenant_ids = network_tenant_ids(db, network_id)

    if payload.audience_kind not in AUDIENCE_KINDS:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип аудитории: {payload.audience_kind}")

    try:
        est = estimate_audience(
            db,
            network_id=network_id,
            tenant_ids=tenant_ids,
            kind=payload.audience_kind,
            params=payload.audience_params,
            exclude_recent_days=payload.exclude_recent_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    warnings: List[str] = []
    wa = get_status(tenant_id=str(tenant_id))
    wa_connected = bool(wa.get("ok") or wa.get("connected"))
    if not wa_connected:
        warnings.append("WhatsApp этого филиала не подключён — рассылку нельзя будет запустить.")

    sent_today = _sent_today_count(db, tenant_id)
    if not _in_send_window():
        warnings.append("Сейчас «тихие часы» (отправка идёт 09:00–21:00) — рассылка начнётся утром.")

    running = db.query(Broadcast).filter(
        Broadcast.tenant_id == tenant_id,
        Broadcast.status == "running",
    ).count()
    if running:
        warnings.append("У этого филиала уже идёт рассылка — новая встанет в очередь после её завершения.")

    return {
        **est,
        "wa_connected": wa_connected,
        "sent_today": sent_today,
        "in_send_window": _in_send_window(),
        "warnings": warnings,
    }


@router.post("")
def create_broadcast(payload: BroadcastCreateIn, request: Request, db: Session = Depends(get_db)):
    """Создаёт черновик рассылки (запуск отдельной кнопкой)."""
    u = require_role(request, *BROADCAST_ROLES)
    tenant_id = must_tenant_id(request)
    network_id = must_network_id(request)

    if payload.audience_kind not in AUDIENCE_KINDS:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип аудитории: {payload.audience_kind}")

    speed = SPEED_PRESETS.get(payload.speed, SPEED_PRESETS["safe"])
    name = (payload.name or "").strip() or f"Рассылка от {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    b = Broadcast(
        tenant_id=tenant_id,
        network_id=network_id,
        name=name,
        message_template=payload.message_template,
        audience_kind=payload.audience_kind,
        audience_json=payload.audience_params or {},
        exclude_recent_days=payload.exclude_recent_days,
        status="draft",
        daily_cap=payload.daily_cap,
        created_by=(u or {}).get("id"),
        **speed,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return _broadcast_out(b)


def start_broadcast_core(db: Session, b: Broadcast) -> Dict[str, Any]:
    """
    Общая логика запуска: проверки → снапшот аудитории → running.
    Используется и новым API, и старым /whatsapp/send-campaign.
    """
    if b.status not in ("draft", "cancelled", "failed"):
        raise HTTPException(status_code=400, detail=f"Рассылку в статусе «{b.status}» нельзя запустить")

    # Один активный процесс на номер (филиал)
    running = db.query(Broadcast).filter(
        Broadcast.tenant_id == b.tenant_id,
        Broadcast.status == "running",
        Broadcast.id != b.id,
    ).first()
    if running:
        raise HTTPException(
            status_code=400,
            detail=f"У этого филиала уже идёт рассылка «{running.name}». Дождитесь завершения или поставьте её на паузу.",
        )

    wa = get_status(tenant_id=str(b.tenant_id))
    if not (wa.get("ok") or wa.get("connected")):
        raise HTTPException(
            status_code=400,
            detail="WhatsApp этого филиала не подключён. Откройте вкладку «Подключение» и отсканируйте QR-код.",
        )

    tenant_ids = network_tenant_ids(db, b.network_id)
    res = build_audience(
        db,
        network_id=b.network_id,
        tenant_ids=tenant_ids,
        kind=b.audience_kind,
        params=b.audience_json or {},
        exclude_recent_days=int(b.exclude_recent_days or 0),
    )
    recipients = res["recipients"]
    if not recipients:
        raise HTTPException(status_code=400, detail="В аудитории нет получателей — рассылку не запускаем.")

    # Чистим возможный старый снапшот (повторный запуск после cancel)
    db.query(WaMessage).filter(
        WaMessage.broadcast_id == b.id,
        WaMessage.status == "pending",
    ).delete(synchronize_session=False)

    for r in recipients:
        db.add(WaMessage(
            broadcast_id=b.id,
            tenant_id=b.tenant_id,
            user_id=r["user_id"],
            phone=r["phone"],
            display_name=r["name"],
            kind="broadcast",
            status="pending",
        ))

    already_processed = int(b.sent or 0) + int(b.failed or 0) + int(b.skipped or 0)
    b.total = already_processed + len(recipients)
    b.status = "running"
    b.started_at = b.started_at or datetime.utcnow()
    b.consecutive_failures = 0
    b.last_error = None
    db.commit()

    start_broadcast_worker()  # на случай если воркер ещё не поднят
    return _broadcast_out(b, {"queued": len(recipients), "excluded": res["excluded"]})


@router.post("/{broadcast_id}/start")
def start_broadcast(broadcast_id: int, request: Request, db: Session = Depends(get_db)):
    """Снапшот аудитории → очередь сообщений → running."""
    require_role(request, *BROADCAST_ROLES)
    network_id = must_network_id(request)
    b = _get_own_broadcast(db, broadcast_id, network_id)
    return start_broadcast_core(db, b)


@router.post("/{broadcast_id}/pause")
def pause_broadcast(broadcast_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, *BROADCAST_ROLES)
    b = _get_own_broadcast(db, broadcast_id, must_network_id(request))
    if b.status != "running":
        raise HTTPException(status_code=400, detail="Рассылка не запущена")
    b.status = "paused"
    db.commit()
    return _broadcast_out(b)


@router.post("/{broadcast_id}/resume")
def resume_broadcast(broadcast_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, *BROADCAST_ROLES)
    b = _get_own_broadcast(db, broadcast_id, must_network_id(request))
    if b.status != "paused":
        raise HTTPException(status_code=400, detail="Рассылка не на паузе")
    b.status = "running"
    b.consecutive_failures = 0
    b.last_error = None
    db.commit()
    start_broadcast_worker()
    return _broadcast_out(b)


@router.post("/{broadcast_id}/cancel")
def cancel_broadcast(broadcast_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, *BROADCAST_ROLES)
    b = _get_own_broadcast(db, broadcast_id, must_network_id(request))
    if b.status not in ("running", "paused", "draft"):
        raise HTTPException(status_code=400, detail="Эту рассылку нельзя отменить")
    # Неотправленные помечаем skipped
    db.query(WaMessage).filter(
        WaMessage.broadcast_id == b.id,
        WaMessage.status == "pending",
    ).update({"status": "skipped", "error": "cancelled"}, synchronize_session=False)
    b.status = "cancelled"
    b.finished_at = datetime.utcnow()
    db.commit()
    return _broadcast_out(b)


@router.post("/test-send")
def test_send(payload: TestSendIn, request: Request, db: Session = Depends(get_db)):
    """Отправить тестовое сообщение (например, себе) с примерными значениями переменных."""
    require_role(request, *BROADCAST_ROLES)
    tenant_id = must_tenant_id(request)

    text = render_message(payload.message_template, {
        "name": "Айгуль",
        "bonus": 3000,
        "tier": "Gold",
        "phone": normalize_phone(payload.phone),
    })
    result = send_message(payload.phone, text, tenant_id=str(tenant_id))
    log_wa_message(
        db,
        tenant_id=tenant_id,
        phone=normalize_phone(payload.phone),
        kind="single",
        status="sent" if result.get("ok") else "failed",
        text=text,
        error=result.get("error"),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Ошибка отправки")
    return {"ok": True, "text": text}


@router.get("")
def list_broadcasts(
    request: Request,
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """История рассылок сети (все филиалы), новые сверху."""
    require_role(request, *BROADCAST_ROLES)
    network_id = must_network_id(request)

    q = (
        db.query(Broadcast)
        .filter(Broadcast.network_id == network_id)
        .order_by(Broadcast.id.desc())
    )
    total = q.count()
    rows = q.offset(offset).limit(limit).all()

    # Имена филиалов-отправителей
    from app.models.auth import Tenant
    tids = {b.tenant_id for b in rows}
    names = {t.id: t.name for t in db.query(Tenant).filter(Tenant.id.in_(tids)).all()} if tids else {}

    return {
        "total": total,
        "items": [_broadcast_out(b, {"sender_name": names.get(b.tenant_id, "")}) for b in rows],
    }


@router.get("/{broadcast_id}")
def get_broadcast(broadcast_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, *BROADCAST_ROLES)
    b = _get_own_broadcast(db, broadcast_id, must_network_id(request))
    return _broadcast_out(b, {
        "in_send_window": _in_send_window(),
        "sent_today": _sent_today_count(db, b.tenant_id),
    })


@router.get("/{broadcast_id}/messages")
def list_broadcast_messages(
    broadcast_id: int,
    request: Request,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    require_role(request, *BROADCAST_ROLES)
    b = _get_own_broadcast(db, broadcast_id, must_network_id(request))

    q = db.query(WaMessage).filter(WaMessage.broadcast_id == b.id)
    if status:
        q = q.filter(WaMessage.status == status)
    total = q.count()
    rows = q.order_by(WaMessage.id.asc()).offset(offset).limit(limit).all()

    def mask(p: str) -> str:
        p = str(p or "")
        return ("*" * max(0, len(p) - 4)) + p[-4:]

    return {
        "total": total,
        "items": [
            {
                "id": m.id,
                "name": m.display_name or "",
                "phone": mask(m.phone),
                "status": m.status,
                "error": m.error,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            }
            for m in rows
        ],
    }
