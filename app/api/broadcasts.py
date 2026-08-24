# app/api/broadcasts.py
"""
API центра WhatsApp-рассылок.

Роутер монтируется под /api/whatsapp/broadcasts — путь /api/whatsapp уже
закрыт ролью owner/admin в AuthGuardMiddleware (main.py, ADMIN_PLUS_PATHS).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_utils import must_tenant_id, must_network_id, network_tenant_ids, require_role
from app.models.broadcast import Broadcast, WaMessage
from app.models.bonus_grant import BonusGrant
from app.models.user import User
from app.services.broadcast_audience import build_audience, estimate_audience, AUDIENCE_KINDS
from app.services.loyalty_engine import get_balances, _now as loyalty_now
from app.services.broadcast_worker import (
    render_message,
    spin,
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
    "safe":     {"delay_min_sec": 7,  "delay_max_sec": 14,  "batch_size": 25, "batch_pause_sec": 90},
    "slow":     {"delay_min_sec": 12, "delay_max_sec": 20,  "batch_size": 20, "batch_pause_sec": 120},
    "fast":     {"delay_min_sec": 4,  "delay_max_sec": 8,   "batch_size": 30, "batch_pause_sec": 60},
    # Для номера, который WhatsApp отключает после ~10 сообщений.
    # Пауза между сообщениями 60–120 сек, каждые 8 сообщений — отдых ~15 мин.
    # Задержка в воркере и так random.uniform(min, max), поэтому разброс
    # получается неровным сам собой — повторяющийся узор выдавал бы бота.
    "turtle":   {"delay_min_sec": 60, "delay_max_sec": 120, "batch_size": 8,  "batch_pause_sec": 900},
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
    try:
        res = build_audience(
            db,
            network_id=b.network_id,
            tenant_ids=tenant_ids,
            kind=b.audience_kind,
            params=b.audience_json or {},
            exclude_recent_days=int(b.exclude_recent_days or 0),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    """
    Отправить тестовое сообщение (например, себе).
    Если номер есть в базе клиентов сети — подставляются его РЕАЛЬНЫЕ
    имя/баланс/уровень, иначе примерные значения.
    """
    require_role(request, *BROADCAST_ROLES)
    tenant_id = must_tenant_id(request)
    network_id = must_network_id(request)

    phone_clean = normalize_phone(payload.phone)

    # Примерные значения по умолчанию
    variables = {"name": "Айгуль", "bonus": 3000, "tier": "Золото", "phone": phone_clean}

    # Реальные данные, если этот номер — клиент сети
    try:
        import hashlib
        from app.core.security import decrypt_field
        from app.models.user import User
        from app.services.loyalty_engine import get_balances
        from app.services.broadcast_worker import TIER_RU

        p_hash = hashlib.sha256(phone_clean.encode()).hexdigest()
        u = db.query(User).filter(
            User.tenant_id == network_id,
            User.phone_hash == p_hash,
        ).first()
        if u:
            balances = get_balances(db, user_id=u.id)
            name = (decrypt_field(u.full_name) or "").strip() if u.full_name else ""
            variables = {
                "name": name or "Клиент",
                "bonus": int(balances.get("available") or 0),
                "tier": TIER_RU.get(u.tier or "", u.tier or ""),
                "phone": phone_clean,
            }
    except Exception:
        pass

    # spin в том же порядке, что и в воркере, — тест должен показывать
    # ровно то, что получит клиент, а не сырые [[а|б]].
    text = spin(render_message(payload.message_template, variables))
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


# ── Массовое начисление бонусов сегменту ─────────────────────
# ВАЖНО: объявлено ДО @router.get("/{broadcast_id}"), иначе путь
# /bulk-bonus уйдёт в него и упадёт на приведении "bulk-bonus" к int.

class BulkBonusIn(AudienceIn):
    """Начисление бонусов той же аудитории, что и рассылка."""
    amount: int = Field(..., ge=1, le=1_000_000)          # бонусов каждому клиенту
    ttl_days: int = Field(default=30, ge=1, le=365)       # срок жизни бонуса
    tag: str = Field(..., min_length=2, max_length=40)    # метка акции: "reactivation-w1"
    dry_run: bool = Field(default=True)                   # True = только посчитать


def _bulk_source(tag: str) -> str:
    return f"bulk:{(tag or '').strip()}"


@router.post("/bulk-bonus")
def bulk_grant_bonus(payload: BulkBonusIn, request: Request, db: Session = Depends(get_db)):
    """
    Разово начисляет бонус всем клиентам сегмента по всей сети (корень + филиалы).

    Идемпотентность: source = "bulk:<tag>". Повторный вызов с тем же tag
    пропустит тех, кому уже начислено — двойного начисления не будет.

    Побочный эффект (полезный): для каждого получателя пересчитывается
    User.bonus_balance через get_balances — сгоревшие гранты помечаются
    expired, фиктивный кэш в карточке клиента исправляется на реальный.
    """
    require_role(request, *BROADCAST_ROLES)
    network_id = must_network_id(request)
    tenant_ids = network_tenant_ids(db, network_id)

    if payload.audience_kind not in AUDIENCE_KINDS:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип аудитории: {payload.audience_kind}")

    # Та же функция, что собирает аудиторию рассылки — списки совпадут 1 в 1.
    try:
        audience = build_audience(
            db,
            network_id=network_id,
            tenant_ids=tenant_ids,
            kind=payload.audience_kind,
            params=payload.audience_params,
            exclude_recent_days=int(payload.exclude_recent_days or 0),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    recipients = audience["recipients"]
    user_ids = [int(r["user_id"]) for r in recipients]
    source = _bulk_source(payload.tag)

    # Кому по этой акции уже начисляли
    already: set[int] = set()
    if user_ids:
        rows = (
            db.query(BonusGrant.user_id)
            .filter(BonusGrant.user_id.in_(user_ids), BonusGrant.source == source)
            .distinct()
            .all()
        )
        already = {int(r[0]) for r in rows}

    to_grant = [uid for uid in user_ids if uid not in already]

    result: Dict[str, Any] = {
        "source": source,
        "tag": payload.tag.strip(),
        "audience_kind": payload.audience_kind,
        "audience_params": payload.audience_params,
        "branches_covered": tenant_ids,
        "audience_total": len(recipients),
        "excluded": audience["excluded"],
        "already_granted": len(already),
        "to_grant": len(to_grant),
        "amount_per_client": int(payload.amount),
        "ttl_days": int(payload.ttl_days),
        "total_bonus_amount": len(to_grant) * int(payload.amount),
        "dry_run": bool(payload.dry_run),
        "sample": [
            {"name": r["name"], "phone": "***" + r["phone"][-4:], "tier": r["tier"], "bonus_now": r["bonus"]}
            for r in recipients[:10]
        ],
    }

    if payload.dry_run:
        result["granted"] = 0
        result["note"] = "Ничего не записано. Повтори с dry_run=false, чтобы начислить."
        return result

    if not to_grant:
        result["granted"] = 0
        result["note"] = "Все клиенты сегмента уже получили бонус по этой акции."
        return result

    # Часы бонусной механики — Алматы (UTC+5), как в loyalty_engine.
    # Берём его же, иначе expires_at разъедется с проверкой сгорания на 5 часов.
    now = loyalty_now()
    expires_at = now + timedelta(days=int(payload.ttl_days))

    granted = 0
    balance_fixed = 0      # у скольких кэш в карточке врал ДО начисления
    balance_delta = 0      # на сколько бонусов суммарно врал (обычно в плюс)
    errors: List[str] = []

    # Пачками по 200 — чтобы длинная транзакция не держала базу
    for i in range(0, len(to_grant), 200):
        chunk = to_grant[i:i + 200]
        try:
            for uid in chunk:
                db.add(BonusGrant(
                    user_id=uid,
                    tenant_id=network_id,       # кошелёк общий на сеть
                    transaction_id=None,
                    amount=int(payload.amount),
                    remaining=int(payload.amount),
                    status="available",         # доступен сразу, без activation_days
                    available_from=now,
                    expires_at=expires_at,
                    source=source,
                ))
            db.commit()
            granted += len(chunk)

            # Пересчёт кэша баланса в карточке клиента.
            # get_balances попутно гасит сгоревшие гранты (process_bonus_lifecycle).
            for uid in chunk:
                u = db.get(User, uid)
                if not u:
                    continue
                old = int(u.bonus_balance or 0)
                new = int(get_balances(db, user_id=uid)["total"])
                # new уже включает свежий грант. Кэш врал, только если старое
                # значение расходится с реальным балансом БЕЗ этого начисления —
                # иначе мы бы считали фиктивным обычный рост у всех подряд.
                was = new - int(payload.amount)
                if old != was:
                    balance_fixed += 1
                    balance_delta += old - was
                u.bonus_balance = new
            db.commit()

        except Exception as e:  # noqa: BLE001
            db.rollback()
            errors.append(f"batch {i}: {e}")

    result["granted"] = granted
    result["balance_cache_fixed"] = balance_fixed
    result["balance_cache_delta"] = balance_delta
    result["expires_at"] = expires_at.isoformat()
    if errors:
        result["errors"] = errors
    return result


def _bulk_report_rows(db: Session, network_id: int, source: str) -> List[BonusGrant]:
    return (
        db.query(BonusGrant)
        .join(User, User.id == BonusGrant.user_id)
        .filter(BonusGrant.source == source, User.tenant_id == network_id)
        .all()
    )


def _bulk_stats(source: str, rows: List[BonusGrant]) -> Dict[str, Any]:
    issued = sum(int(g.amount or 0) for g in rows)
    left = sum(int(g.remaining or 0) for g in rows)
    used_clients = sum(1 for g in rows if int(g.remaining or 0) < int(g.amount or 0))
    created = [g.created_at for g in rows if g.created_at]
    expires = [g.expires_at for g in rows if g.expires_at]
    return {
        "source": source,
        "tag": source[len("bulk:"):] if source.startswith("bulk:") else source,
        "clients": len(rows),
        "issued": issued,
        "remaining": left,
        "used": issued - left,
        "used_percent": round((issued - left) / issued * 100, 1) if issued else 0.0,
        "clients_activated": used_clients,
        "activation_percent": round(used_clients / len(rows) * 100, 1) if rows else 0.0,
        "expired": sum(1 for g in rows if g.status == "expired"),
        "amount_per_client": int(rows[0].amount or 0) if rows else 0,
        "granted_at": min(created).isoformat() if created else None,
        "expires_at": max(expires).isoformat() if expires else None,
    }


@router.get("/bulk-bonus")
def bulk_bonus_list(request: Request, db: Session = Depends(get_db)):
    """Список акций массового начисления сети — для выпадающего списка в отчёте."""
    require_role(request, *BROADCAST_ROLES)
    network_id = must_network_id(request)

    rows = (
        db.query(BonusGrant)
        .join(User, User.id == BonusGrant.user_id)
        .filter(BonusGrant.source.like("bulk:%"), User.tenant_id == network_id)
        .all()
    )
    by_source: Dict[str, List[BonusGrant]] = {}
    for g in rows:
        by_source.setdefault(g.source, []).append(g)

    items = [_bulk_stats(src, grants) for src, grants in by_source.items()]
    items.sort(key=lambda it: it["granted_at"] or "", reverse=True)
    return {"items": items}


@router.get("/bulk-bonus/{tag}")
def bulk_bonus_report(tag: str, request: Request, db: Session = Depends(get_db)):
    """Отчёт по акции: начислено / потрачено / сгорело."""
    require_role(request, *BROADCAST_ROLES)
    network_id = must_network_id(request)

    source = _bulk_source(tag)
    return _bulk_stats(source, _bulk_report_rows(db, network_id, source))


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
