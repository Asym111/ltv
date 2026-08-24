# app/services/wa_health.py
"""
Наблюдение за WhatsApp-сессиями всех тенантов для панели суперадмина.

Фоновая проверка опрашивает WA-сервис по каждому активному тенанту и пишет
в базу последнее известное состояние. Событие в ленту уведомлений создаётся
только на ПЕРЕХОДЕ состояния — иначе лента заполнится копиями одной строки.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.auth import Tenant
from app.models.wa_health import WaHealthEvent, WaSessionState
from app.services.whatsapp import _is_configured, get_status

logger = logging.getLogger(__name__)

# tenant_id для событий уровня платформы (лёг сам WA-сервис, а не сессия компании)
PLATFORM_TENANT_ID = 0


def _tenant_label(t: Tenant) -> str:
    return (t.name or "").strip() or f"Тенант #{t.id}"


def _open_disconnect(db: Session, tenant_id: int) -> Optional[WaHealthEvent]:
    """Незакрытая тревога об отключении по тенанту, если она есть."""
    return (
        db.query(WaHealthEvent)
        .filter(
            WaHealthEvent.tenant_id == tenant_id,
            WaHealthEvent.event == "disconnected",
            WaHealthEvent.resolved_at.is_(None),
        )
        .order_by(WaHealthEvent.id.desc())
        .first()
    )


def _add_event(db: Session, tenant_id: int, name: str, event: str, detail: str = "") -> None:
    db.add(WaHealthEvent(
        tenant_id=tenant_id,
        tenant_name=name,
        event=event,
        detail=(detail or "")[:500] or None,
        created_at=datetime.utcnow(),
    ))


def check_all_sessions(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Опрашивает WA-сервис по всем активным тенантам и обновляет состояние.
    Возвращает сводку — её же показываем при ручной проверке из панели.
    """
    own_session = db is None
    db = db or SessionLocal()
    try:
        if not _is_configured():
            return {"ok": False, "checked": 0,
                    "error": "WA-сервис не настроен (WA_SERVICE_URL / WA_INTERNAL_TOKEN)"}

        tenants: List[Tenant] = db.query(Tenant).filter(Tenant.is_active == True).all()  # noqa: E712
        if not tenants:
            return {"ok": True, "checked": 0, "connected": 0, "disconnected": 0}

        now = datetime.utcnow()

        # Сначала опрашиваем всех, потом решаем — иначе не отличить
        # «упал WA-сервис целиком» от «отключилась одна компания».
        probes: List[Dict[str, Any]] = []
        for t in tenants:
            st = get_status(t.id) or {}
            probes.append({
                "tenant": t,
                "connected": bool(st.get("ok") or st.get("connected")),
                "error": st.get("error"),
            })

        transport_down = all(p["error"] for p in probes)
        if transport_down:
            # Не поднимаем тревогу по каждой компании — проблема одна и общая.
            detail = str(probes[0]["error"])[:500]
            if not _open_disconnect(db, PLATFORM_TENANT_ID):
                _add_event(db, PLATFORM_TENANT_ID, "WhatsApp-сервис",
                           "disconnected", f"WA-сервис недоступен: {detail}")
            db.commit()
            logger.warning("[wa-health] WA-сервис недоступен: %s", detail)
            return {"ok": False, "checked": len(probes), "connected": 0,
                    "disconnected": 0, "service_down": True, "error": detail}

        # Сервис жив — закрываем тревогу уровня платформы, если висела
        plat = _open_disconnect(db, PLATFORM_TENANT_ID)
        if plat:
            plat.resolved_at = now
            _add_event(db, PLATFORM_TENANT_ID, "WhatsApp-сервис", "connected", "Сервис снова отвечает")

        connected_n = 0
        went_down: List[str] = []
        came_up: List[str] = []

        for p in probes:
            t: Tenant = p["tenant"]
            connected: bool = p["connected"]
            if connected:
                connected_n += 1

            row = db.get(WaSessionState, t.id)
            if row is None:
                # Первая встреча с тенантом: только фиксируем состояние.
                # Про того, кого раньше не видели, нельзя сказать «отключился».
                db.add(WaSessionState(
                    tenant_id=t.id,
                    connected=connected,
                    last_checked_at=now,
                    last_connected_at=now if connected else None,
                    last_change_at=now,
                    last_error=p["error"],
                    ever_connected=connected,
                ))
                continue

            was = bool(row.connected)
            row.last_checked_at = now
            row.last_error = p["error"]
            if connected:
                row.last_connected_at = now
                row.ever_connected = True

            if was == connected:
                continue

            row.connected = connected
            row.last_change_at = now

            if not connected:
                # Тревога только про тех, у кого WhatsApp когда-то работал.
                if row.ever_connected and not _open_disconnect(db, t.id):
                    _add_event(db, t.id, _tenant_label(t), "disconnected",
                               p["error"] or "Сессия WhatsApp отключилась")
                    went_down.append(_tenant_label(t))
            else:
                open_ev = _open_disconnect(db, t.id)
                if open_ev:
                    open_ev.resolved_at = now
                _add_event(db, t.id, _tenant_label(t), "connected", "Подключение восстановлено")
                came_up.append(_tenant_label(t))

        db.commit()

        if went_down:
            logger.warning("[wa-health] отключился WhatsApp: %s", ", ".join(went_down))
        if came_up:
            logger.info("[wa-health] восстановлен WhatsApp: %s", ", ".join(came_up))

        return {
            "ok": True,
            "checked": len(probes),
            "connected": connected_n,
            "disconnected": len(probes) - connected_n,
            "went_down": went_down,
            "came_up": came_up,
        }
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error("[wa-health] проверка упала: %s", e)
        return {"ok": False, "error": str(e), "checked": 0}
    finally:
        if own_session:
            db.close()


def list_alerts(db: Session, limit: int = 30) -> Dict[str, Any]:
    """
    Лента для панели суперадмина:
      active — сейчас лежит (незакрытые отключения),
      recent — история последних событий.
    """
    active = (
        db.query(WaHealthEvent)
        .filter(WaHealthEvent.event == "disconnected", WaHealthEvent.resolved_at.is_(None))
        .order_by(WaHealthEvent.created_at.desc())
        .all()
    )
    recent = (
        db.query(WaHealthEvent)
        .order_by(WaHealthEvent.id.desc())
        .limit(limit)
        .all()
    )
    unread = sum(1 for e in active if e.acknowledged_at is None)
    return {"active": active, "recent": recent, "unread": unread}


def states_by_tenant(db: Session) -> Dict[int, WaSessionState]:
    return {int(r.tenant_id): r for r in db.query(WaSessionState).all()}
