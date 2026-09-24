# app/services/broadcast_worker.py
"""
Фоновый воркер WhatsApp-рассылок.

Принципы безопасности (анти-бан):
  - случайная задержка delay_min..delay_max сек между сообщениями
  - каждые batch_size сообщений — длинная пауза batch_pause_sec (±30%)
  - дневной лимит daily_cap на номер (тенант-отправитель)
  - тихие часы: отправка только 09:00–21:00 по Алматы
  - предохранитель: 5 ошибок подряд → рассылка ставится на паузу
  - повторная проверка wa_opt_out прямо перед отправкой

Надёжность:
  - всё состояние в БД (broadcasts + wa_messages), в памяти ничего нет
  - короткие транзакции: commit после каждого сообщения
  - после рестарта приложения running-рассылки продолжаются сами
  - один воркер-поток на процесс; несколько running-рассылок обслуживаются
    по кругу (round-robin), каждая со своим темпом (next_at)

Управление: pause/resume/cancel меняют Broadcast.status — воркер видит это
на следующей итерации.
"""
from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings as env_settings
from app.core.database import SessionLocal
from app.models.broadcast import Broadcast, WaMessage
from app.models.user import User
from app.services.whatsapp import send_message
from app.services.loyalty_engine import get_balances, ALMATY

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except Exception:
        return default


# Тихие часы: отправляем только в этом окне (локальное время Алматы).
# Переопределяется через env WA_QUIET_START / WA_QUIET_END.
QUIET_HOURS_START = _int_env("WA_QUIET_START", 9)   # с 09:00
QUIET_HOURS_END = _int_env("WA_QUIET_END", 21)      # до 21:00

# Предохранитель: сколько ошибок подряд до автопаузы
CIRCUIT_BREAKER_FAILS = 5

_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
# Темп каждой рассылки: broadcast_id -> (time.monotonic, когда можно следующее)
_next_at: dict[int, float] = {}
_sent_in_batch: dict[int, int] = {}


def _now_almaty() -> datetime:
    return datetime.now(ALMATY).replace(tzinfo=None)


def _in_send_window(now: datetime | None = None) -> bool:
    now = now or _now_almaty()
    return QUIET_HOURS_START <= now.hour < QUIET_HOURS_END


def _sent_today_count(db: Session, tenant_id: int, channel: str | None = None) -> int:
    """Сколько сообщений уже отправлено сегодня с номера этого тенанта (опц. — по каналу)."""
    start = datetime.combine(_now_almaty().date(), datetime.min.time())
    q = (
        db.query(func.count(WaMessage.id))
        .filter(
            WaMessage.tenant_id == tenant_id,
            WaMessage.status == "sent",
            WaMessage.sent_at >= start,
        )
    )
    if channel:
        q = q.filter(WaMessage.channel == channel)
    return int(q.scalar() or 0)


# ── Рендер сообщения ──────────────────────────────────────────

RU_ALIASES = {
    "имя": "name",
    "бонусы": "bonus",
    "бонус": "bonus",
    "уровень": "tier",
    "телефон": "phone",
}

# Уровни в сообщениях клиентам — по-русски
TIER_RU = {"Bronze": "Бронза", "Silver": "Серебро", "Gold": "Золото"}


_SPIN_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


def spin(text: str) -> str:
    """
    Разворачивает [[вариант1|вариант2|вариант3]] в один случайный вариант.

    Зачем: 3243 идентичных сообщения подряд — самый явный признак бота для
    антиспама WhatsApp. Каждый получатель получает свою формулировку, смысл
    при этом сохраняется.

    Пример шаблона:
        [[Здравствуйте|Добрый день|Приветствуем]], {имя}!
        [[Давно вас не видели|Вы давно к нам не заглядывали]].

    Вложенность не поддерживается — намеренно, чтобы шаблон оставался
    читаемым для менеджера.
    """
    def _pick(m: re.Match) -> str:
        options = [o.strip() for o in m.group(1).split("|") if o.strip()]
        return random.choice(options) if options else ""

    # Несколько проходов не нужны: вложенностей нет
    return _SPIN_RE.sub(_pick, str(text or ""))


def render_message(template: str, variables: dict) -> str:
    """
    Подставляет переменные. Поддерживает русские алиасы {имя} {бонусы} {уровень}
    и легаси {name} {bonus} {tier} {phone}. Недостающие переменные не роняют шаблон.
    """
    text = str(template or "")
    merged = dict(variables or {})
    for ru, en in RU_ALIASES.items():
        if en in merged:
            merged[ru] = merged[en]

    for key, value in merged.items():
        text = text.replace("{" + str(key) + "}", str(value))
    return text


def render_for_user(db: Session, template: str, msg: WaMessage) -> str:
    """Рендер с ЖИВЫМ балансом бонусов на момент отправки."""
    bonus = 0
    tier = ""
    name = msg.display_name or "Клиент"
    if msg.user_id:
        try:
            user = db.get(User, int(msg.user_id))
            if user is not None:
                tier = TIER_RU.get(user.tier or "", user.tier or "")
                balances = get_balances(db, user_id=user.id)
                bonus = int(balances.get("available") or 0)
        except Exception as e:
            logger.warning(f"render_for_user balances failed user={msg.user_id}: {e}")

    # Порядок важен: сначала подставляются переменные, потом выбирается
    # вариант. Иначе [[...]] внутри значения переменной не развернулись бы.
    return spin(render_message(template, {
        "name": name,
        "bonus": bonus,
        "tier": tier,
        "phone": msg.phone,
    }))


def _user_variables(db: Session, msg: WaMessage) -> dict:
    """Переменные клиента с ЖИВЫМ балансом на момент отправки."""
    bonus = 0
    tier = ""
    name = msg.display_name or "Клиент"
    if msg.user_id:
        try:
            user = db.get(User, int(msg.user_id))
            if user is not None:
                tier = TIER_RU.get(user.tier or "", user.tier or "")
                balances = get_balances(db, user_id=user.id)
                bonus = int(balances.get("available") or 0)
        except Exception as e:
            logger.warning(f"_user_variables failed user={msg.user_id}: {e}")
    first = (name or "").split()[0] if name else "Клиент"
    return {"name": name, "first_name": first, "bonus": bonus, "tier": tier, "phone": msg.phone}


# ── Основной цикл ─────────────────────────────────────────────

def _process_one(db: Session, b: Broadcast) -> bool:
    """
    Отправляет одно pending-сообщение рассылки.
    Возвращает True, если сообщение было обработано (отправлено/пропущено/ошибка).
    """
    msg: WaMessage | None = (
        db.query(WaMessage)
        .filter(WaMessage.broadcast_id == b.id, WaMessage.status == "pending")
        .order_by(WaMessage.id.asc())
        .first()
    )

    if msg is None:
        # Готово — фиксируем завершение
        b.status = "done"
        b.finished_at = datetime.utcnow()
        db.commit()
        logger.info(f"[broadcast {b.id}] done: sent={b.sent} failed={b.failed} skipped={b.skipped}")
        _next_at.pop(b.id, None)
        _sent_in_batch.pop(b.id, None)
        return False

    # Повторная проверка отписки прямо перед отправкой
    if msg.user_id:
        try:
            u = db.get(User, int(msg.user_id))
            if u is not None and bool(getattr(u, "wa_opt_out", False)):
                msg.status = "skipped"
                msg.error = "opt_out"
                b.skipped = int(b.skipped or 0) + 1
                db.commit()
                return True
        except Exception:
            pass

    # Серые массовые рассылки отключены: номер ltv-wa-service используется
    # только для уведомлений по бонусам, иначе его банят.
    if (b.channel or "gray") != "official":
        b.status = "paused"
        b.last_error = (
            "Рассылки через подключённый по QR WhatsApp отключены, чтобы номер не блокировали. "
            "Создайте рассылку заново — она пойдёт через официальный WhatsApp."
        )
        db.commit()
        return False

    return _process_official(db, b, msg)


def _process_official(db: Session, b: Broadcast, msg: WaMessage) -> bool:
    """Отправка одного сообщения рассылки через официальный WhatsApp (шаблон + кредит)."""
    import json
    from app.services import wa_credits
    from app.services.wa_official import get_channel, send_template, render_params

    try:
        tpl = json.loads(b.wa_template_params or "{}")
    except Exception:
        tpl = {}
    param_tpls = tpl.get("params") or []
    param_names = tpl.get("names") or []

    variables = _user_variables(db, msg)
    params = render_params(param_tpls, variables)
    # Для журнала и тест-просмотра — текст шаблона с подставленными значениями
    body = str(tpl.get("body") or b.message_template or "")
    preview = body
    for i, name in enumerate(param_names):
        if i < len(params):
            preview = preview.replace("{{" + str(name) + "}}", params[i])

    # 1 кредит = 1 сообщение. Нет кредитов — пауза, сообщение остаётся в очереди.
    if not wa_credits.charge(db, b.network_id, 1, broadcast_id=b.id):
        db.rollback()
        b.status = "paused"
        b.last_error = "Закончились кредиты на рассылку. Пополните баланс — рассылка продолжится с того же места."
        db.commit()
        return False

    ch = get_channel(db, b.tenant_id, b.network_id)
    result = send_template(ch, msg.phone, b.wa_template_name or "", b.wa_template_lang or "ru",
                           params, param_names)

    msg.text = preview
    msg.channel = "official"
    if result.get("ok"):
        msg.status = "sent"
        msg.sent_at = datetime.utcnow()
        msg.provider_message_id = result.get("message_id")
        msg.credits_charged = 1
        msg.error = None
        b.sent = int(b.sent or 0) + 1
        b.consecutive_failures = 0
        db.commit()
        return True

    # Не ушло — кредит возвращаем
    wa_credits.refund(db, b.network_id, 1, broadcast_id=b.id)
    err = str(result.get("error") or "unknown")[:490]

    if result.get("retryable"):
        # Лимит скорости/временный сбой: сообщение остаётся pending, ждём
        msg.error = err
        b.consecutive_failures = int(b.consecutive_failures or 0) + 1
        _next_at[b.id] = time.monotonic() + min(600, 30 * b.consecutive_failures)
        if b.consecutive_failures >= CIRCUIT_BREAKER_FAILS * 2:
            b.status = "paused"
            b.last_error = f"WhatsApp временно ограничил отправку. Продолжите позже. Ошибка: {err}"
        db.commit()
        return False

    if result.get("fatal"):
        # Ключ/шаблон/номер: дальше слать бессмысленно
        msg.error = err
        b.status = "paused"
        b.last_error = f"Официальный WhatsApp отклонил отправку: {err}"
        db.commit()
        return False

    msg.status = "failed"
    msg.error = err
    b.failed = int(b.failed or 0) + 1
    b.consecutive_failures = int(b.consecutive_failures or 0) + 1
    if b.consecutive_failures >= CIRCUIT_BREAKER_FAILS * 4:
        b.status = "paused"
        b.last_error = f"Много ошибок подряд. Последняя: {err}"
    db.commit()
    return True


def _legacy_gray_send(db: Session, b: Broadcast, msg: WaMessage) -> bool:
    """Старая отправка через серый номер. Не вызывается — оставлена для отката."""
    text = render_for_user(db, b.message_template, msg)

    result = send_message(msg.phone, text, tenant_id=str(b.tenant_id))

    msg.text = text
    if result.get("ok"):
        msg.status = "sent"
        msg.sent_at = datetime.utcnow()
        b.sent = int(b.sent or 0) + 1
        b.consecutive_failures = 0
    else:
        msg.status = "failed"
        msg.error = str(result.get("error") or "unknown")[:490]
        b.failed = int(b.failed or 0) + 1
        b.consecutive_failures = int(b.consecutive_failures or 0) + 1
        logger.warning(f"[broadcast {b.id}] send failed to ...{msg.phone[-4:]}: {msg.error}")

        if b.consecutive_failures >= CIRCUIT_BREAKER_FAILS:
            b.status = "paused"
            b.last_error = (
                f"Остановлено: {CIRCUIT_BREAKER_FAILS} ошибок подряд. "
                f"Проверьте подключение WhatsApp этого филиала и нажмите «Продолжить». "
                f"Последняя ошибка: {msg.error}"
            )
            logger.warning(f"[broadcast {b.id}] circuit breaker → paused")

    db.commit()
    return True


def _schedule_next(b: Broadcast) -> None:
    """Назначает время следующей отправки с учётом пакетов."""
    delay = random.uniform(max(1, b.delay_min_sec or 7), max(2, b.delay_max_sec or 14))

    _sent_in_batch[b.id] = _sent_in_batch.get(b.id, 0) + 1
    if b.batch_size and _sent_in_batch[b.id] >= int(b.batch_size):
        _sent_in_batch[b.id] = 0
        base = max(10, int(b.batch_pause_sec or 90))
        delay += base * random.uniform(0.7, 1.3)
        logger.info(f"[broadcast {b.id}] batch pause ~{int(delay)}s")

    _next_at[b.id] = time.monotonic() + delay


def _worker_loop() -> None:
    logger.info("[broadcast-worker] started")
    while True:
        try:
            db: Session = SessionLocal()
            try:
                running: list[Broadcast] = (
                    db.query(Broadcast)
                    .filter(Broadcast.status == "running")
                    .order_by(Broadcast.id.asc())
                    .all()
                )

                if not running:
                    time.sleep(3)
                    continue

                if not _in_send_window():
                    # Тихие часы: ждём открытия окна
                    time.sleep(60)
                    continue

                now_mono = time.monotonic()
                did_something = False

                for b in running:
                    if _next_at.get(b.id, 0) > now_mono:
                        continue

                    # Дневной лимит номера-отправителя
                    if _sent_today_count(db, b.tenant_id, b.channel or "gray") >= int(b.daily_cap or 250):
                        # Лимит достигнут — проверим снова через 10 минут
                        _next_at[b.id] = now_mono + 600
                        if not (b.last_error or "").startswith("Дневной лимит"):
                            b.last_error = (
                                f"Дневной лимит {b.daily_cap} сообщений достигнут — "
                                f"рассылка продолжится завтра автоматически."
                            )
                            db.commit()
                        continue

                    processed = _process_one(db, b)
                    if processed:
                        did_something = True
                        _schedule_next(b)

                time.sleep(1 if did_something else 2)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[broadcast-worker] loop error: {e}", exc_info=True)
            time.sleep(5)


def start_broadcast_worker() -> None:
    """Идемпотентный запуск воркера (вызывается на startup приложения)."""
    global _worker_thread

    enabled = bool(getattr(env_settings, "BROADCAST_WORKER_ENABLED", True))
    if not enabled:
        logger.info("[broadcast-worker] disabled via BROADCAST_WORKER_ENABLED")
        return

    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="broadcast-worker",
            daemon=True,
        )
        _worker_thread.start()


def log_wa_message(
    db: Session,
    tenant_id: int,
    phone: str,
    kind: str,
    status: str,
    text: str | None = None,
    user_id: int | None = None,
    error: str | None = None,
    display_name: str | None = None,
) -> None:
    """Best-effort запись в журнал сообщений (для одиночных и авто-отправок)."""
    try:
        row = WaMessage(
            broadcast_id=None,
            tenant_id=int(tenant_id),
            user_id=user_id,
            phone=str(phone or "")[:32],
            display_name=display_name,
            kind=kind,
            text=text,
            status=status,
            error=(str(error)[:490] if error else None),
            sent_at=datetime.utcnow() if status == "sent" else None,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"log_wa_message failed: {e}")
