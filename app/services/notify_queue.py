# app/services/notify_queue.py
"""
Очередь сервисных WhatsApp-уведомлений через «серый» номер (ltv-wa-service).

Сюда идут ТОЛЬКО уведомления по бонусам: начисление/списание, возврат,
день рождения, сгорание бонусов, смена уровня. Массовые рассылки через серый
номер больше не отправляются — они идут через официальный WhatsApp.

Зачем очередь, а не отправка прямо из запроса:
  - кассир не ждёт 3–8 секунд «печатает…» при каждой продаже;
  - сообщения одного номера уходят строго по одному и с паузой — никаких
    пачек подряд, которые антиспам WhatsApp воспринимает как рассылку;
  - если сессия отвалилась, сообщения не «сгорают» ошибкой, а ждут
    переподключения (и устаревают, если ждать слишком долго);
  - ночные задачи (ДР, сгорание) не выстреливают сотней сообщений за минуту,
    а расходятся по дню с дневным лимитом на номер.

Приоритеты:
  0 — чек по транзакции / возврат (уходит первым, короткая пауза)
  1 — напоминания (ДР, сгорание, уровень): длинные паузы, только днём,
      дневной лимит на номер

Запись в журнал — та же таблица wa_messages (kind="auto", broadcast_id=NULL),
поэтому история видна в разделе WhatsApp как раньше.
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import text, func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.broadcast import WaMessage

logger = logging.getLogger(__name__)

PRIORITY_TRANSACTIONAL = 0
PRIORITY_REMINDER = 1


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except Exception:
        return default


# Паузы между сообщениями ОДНОГО номера (сек)
TX_GAP_MIN = _int_env("WA_NOTIFY_TX_GAP_MIN", 8)
TX_GAP_MAX = _int_env("WA_NOTIFY_TX_GAP_MAX", 15)
REMINDER_GAP_MIN = _int_env("WA_NOTIFY_REMINDER_GAP_MIN", 45)
REMINDER_GAP_MAX = _int_env("WA_NOTIFY_REMINDER_GAP_MAX", 120)

# Напоминания — только днём по Алматы и не больше N в день с номера
REMINDER_HOUR_START = _int_env("WA_NOTIFY_HOUR_START", 10)
REMINDER_HOUR_END = _int_env("WA_NOTIFY_HOUR_END", 20)
REMINDER_DAILY_CAP = _int_env("WA_NOTIFY_REMINDER_DAILY_CAP", 60)

# Сколько сообщение может ждать отправки, прежде чем стать неактуальным
TX_MAX_AGE_HOURS = _int_env("WA_NOTIFY_TX_MAX_AGE_HOURS", 12)
REMINDER_MAX_AGE_HOURS = _int_env("WA_NOTIFY_REMINDER_MAX_AGE_HOURS", 36)

MAX_ATTEMPTS = 3
# Сессия номера не подключена — не долбим сервис, ждём
SESSION_DOWN_BACKOFF_SEC = 300

_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
_next_at: dict[int, float] = {}       # tenant_id -> monotonic, когда можно следующее


def _now_almaty() -> datetime:
    from app.services.loyalty_engine import ALMATY
    return datetime.now(ALMATY).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────
# Постановка в очередь
# ─────────────────────────────────────────────────────────────
def enqueue_notification(
    db: Session,
    tenant_id: int,
    phone: str,
    text_: str,
    user_id: int | None = None,
    priority: int = PRIORITY_TRANSACTIONAL,
) -> None:
    """Ставит сервисное уведомление в очередь. Никогда не бросает исключений."""
    try:
        from app.services.whatsapp import normalize_phone
        p = normalize_phone(phone)
        if len(p) < 11 or not text_:
            return
        row = WaMessage(
            broadcast_id=None,
            tenant_id=int(tenant_id),
            user_id=user_id,
            phone=p[:32],
            kind="auto",
            text=text_,
            status="pending",
            priority=int(priority),
            attempts=0,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"enqueue_notification failed: {e}")


# ─────────────────────────────────────────────────────────────
# Воркер
# ─────────────────────────────────────────────────────────────
def _claim(db: Session, msg_id: int) -> bool:
    """Атомарно забирает сообщение (защита от двойной отправки при нескольких процессах)."""
    res = db.execute(
        text("UPDATE wa_messages SET status='sending' WHERE id=:id AND status='pending'"),
        {"id": msg_id},
    )
    db.commit()
    return (res.rowcount or 0) == 1


def _reminders_sent_today(db: Session, tenant_id: int) -> int:
    start = datetime.combine(_now_almaty().date(), datetime.min.time())
    # sent_at пишется в UTC, окно ±5 часов на границе дня нам не критично
    return int(
        db.query(func.count(WaMessage.id))
        .filter(
            WaMessage.tenant_id == tenant_id,
            WaMessage.broadcast_id.is_(None),
            WaMessage.kind == "auto",
            WaMessage.priority == PRIORITY_REMINDER,
            WaMessage.status == "sent",
            WaMessage.sent_at >= start - timedelta(hours=5),
        )
        .scalar() or 0
    )


def _is_session_down(result: dict) -> bool:
    err = str(result.get("error") or "").lower()
    return (
        result.get("status") in (503, 429)
        or "не подключ" in err
        or "session_inactive" in err
        or "busy" in err
        or "не настроен" in err
    )


def _expire_stale(db: Session) -> None:
    now = datetime.utcnow()
    for prio, hours in (
        (PRIORITY_TRANSACTIONAL, TX_MAX_AGE_HOURS),
        (PRIORITY_REMINDER, REMINDER_MAX_AGE_HOURS),
    ):
        db.query(WaMessage).filter(
            WaMessage.broadcast_id.is_(None),
            WaMessage.kind == "auto",
            WaMessage.status == "pending",
            WaMessage.priority == prio,
            WaMessage.created_at < now - timedelta(hours=hours),
        ).update(
            {WaMessage.status: "skipped", WaMessage.error: "expired: WhatsApp был недоступен слишком долго"},
            synchronize_session=False,
        )
    db.commit()


def _tick(db: Session) -> bool:
    """Одна итерация. Возвращает True, если что-то отправили."""
    from app.services.whatsapp import send_message

    now_mono = time.monotonic()
    now_local = _now_almaty()
    reminder_window = REMINDER_HOUR_START <= now_local.hour < REMINDER_HOUR_END

    # Тенанты, у которых есть очередь
    tenants = [
        int(r[0]) for r in
        db.query(WaMessage.tenant_id)
        .filter(
            WaMessage.broadcast_id.is_(None),
            WaMessage.kind == "auto",
            WaMessage.status == "pending",
        )
        .distinct()
        .all()
    ]

    sent_any = False
    for tid in tenants:
        if _next_at.get(tid, 0) > now_mono:
            continue

        q = (
            db.query(WaMessage)
            .filter(
                WaMessage.tenant_id == tid,
                WaMessage.broadcast_id.is_(None),
                WaMessage.kind == "auto",
                WaMessage.status == "pending",
            )
        )
        if not reminder_window or _reminders_sent_today(db, tid) >= REMINDER_DAILY_CAP:
            q = q.filter(WaMessage.priority == PRIORITY_TRANSACTIONAL)

        msg = q.order_by(WaMessage.priority.asc(), WaMessage.id.asc()).first()
        if msg is None or not _claim(db, msg.id):
            continue
        db.refresh(msg)

        result = send_message(msg.phone, msg.text or "", tenant_id=str(tid))

        if result.get("ok"):
            msg.status = "sent"
            msg.sent_at = datetime.utcnow()
            msg.error = None
            sent_any = True
            if int(msg.priority or 0) == PRIORITY_TRANSACTIONAL:
                gap = random.uniform(TX_GAP_MIN, TX_GAP_MAX)
            else:
                gap = random.uniform(REMINDER_GAP_MIN, REMINDER_GAP_MAX)
            _next_at[tid] = time.monotonic() + gap
        elif _is_session_down(result):
            # Номер не подключён / сервис занят — вернём в очередь, попытку не тратим
            msg.status = "pending"
            msg.error = str(result.get("error") or "")[:490]
            _next_at[tid] = time.monotonic() + SESSION_DOWN_BACKOFF_SEC
            logger.info(f"[notify] tenant={tid} WhatsApp недоступен — пауза {SESSION_DOWN_BACKOFF_SEC}s")
        else:
            msg.attempts = int(msg.attempts or 0) + 1
            msg.error = str(result.get("error") or "unknown")[:490]
            msg.status = "failed" if msg.attempts >= MAX_ATTEMPTS else "pending"
            _next_at[tid] = time.monotonic() + random.uniform(30, 60)
        db.commit()

    return sent_any


def _worker_loop() -> None:
    logger.info("[notify-worker] started")
    last_expire = 0.0
    # После рестарта «зависшие» sending возвращаем в очередь
    try:
        db = SessionLocal()
        db.execute(text(
            "UPDATE wa_messages SET status='pending' "
            "WHERE status='sending' AND broadcast_id IS NULL AND kind='auto'"
        ))
        db.commit()
        db.close()
    except Exception as e:
        logger.warning(f"[notify-worker] reset sending failed: {e}")

    while True:
        try:
            db: Session = SessionLocal()
            try:
                if time.monotonic() - last_expire > 600:
                    _expire_stale(db)
                    last_expire = time.monotonic()
                did = _tick(db)
            finally:
                db.close()
            time.sleep(1 if did else 3)
        except Exception as e:
            logger.error(f"[notify-worker] loop error: {e}", exc_info=True)
            time.sleep(10)


def start_notify_worker() -> None:
    """Идемпотентный запуск (вызывается на startup)."""
    global _worker_thread
    if str(os.getenv("WA_NOTIFY_WORKER_ENABLED", "true")).lower() in ("0", "false", "no", "off"):
        logger.info("[notify-worker] disabled via WA_NOTIFY_WORKER_ENABLED")
        return
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_worker_loop, name="notify-worker", daemon=True)
        _worker_thread.start()
