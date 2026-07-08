from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.core.config import settings as env_settings
from app.models.settings_model import Settings
from app.models.bonus_grant import BonusGrant

# UTC+5 Алматы — единый timezone для всего приложения
ALMATY = timezone(timedelta(hours=5))


def _now() -> datetime:
    """Текущее время Алматы (UTC+5), naive для совместимости с БД."""
    return datetime.now(ALMATY).replace(tzinfo=None)


def resolve_network_id(db: Session, tenant_id: int | None) -> int | None:
    """
    Корень сети для тенанта: если это филиал (parent_tenant_id задан) —
    возвращает id головного тенанта, иначе сам tenant_id.
    """
    if not tenant_id:
        return None
    from app.models.auth import Tenant
    t = db.get(Tenant, int(tenant_id))
    if t is not None and t.parent_tenant_id:
        return int(t.parent_tenant_id)
    return int(tenant_id)


def get_or_create_settings(db: Session, tenant_id: int | None = None) -> Settings:
    """
    Настройки тенанта. Если своих нет — создаёт копию глобального шаблона
    (tenant_id IS NULL) или дефолты из env. НИКОГДА не возвращает строку
    другого тенанта.
    """
    if tenant_id:
        row = db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
        if row:
            return row
        template = db.query(Settings).filter(Settings.tenant_id == None).first()  # noqa: E711
    else:
        row = db.query(Settings).filter(Settings.tenant_id == None).first()  # noqa: E711
        if row:
            return row
        template = None

    d = {}
    if template:
        for col in template.__table__.columns:
            if col.name not in ("id", "tenant_id", "created_at"):
                d[col.name] = getattr(template, col.name)

    row = Settings(
        tenant_id=tenant_id,
        bonus_name=d.get("bonus_name", "баллы"),
        earn_bronze_percent=d.get("earn_bronze_percent", int(env_settings.BONUS_PERCENT_BRONZE)),
        earn_silver_percent=d.get("earn_silver_percent", int(env_settings.BONUS_PERCENT_SILVER)),
        earn_gold_percent=d.get("earn_gold_percent",   int(env_settings.BONUS_PERCENT_GOLD)),
        welcome_bonus_percent=d.get("welcome_bonus_percent", 0),
        redeem_max_percent=d.get("redeem_max_percent", int(env_settings.REDEEM_MAX_PERCENT)),
        activation_days=d.get("activation_days", int(env_settings.BONUS_ACTIVATION_DAYS)),
        burn_days=d.get("burn_days", int(env_settings.BONUS_BURN_DAYS)),
        burn_percent=d.get("burn_percent", 100),
        birthday_bonus_amount=d.get("birthday_bonus_amount", int(env_settings.BDAY_BONUS_AMOUNT)),
        birthday_bonus_days_before=d.get("birthday_bonus_days_before", 7),
        birthday_bonus_ttl_days=d.get("birthday_bonus_ttl_days", 30),
        birthday_notify_7d=d.get("birthday_notify_7d", True),
        birthday_notify_3d=d.get("birthday_notify_3d", True),
        birthday_notify_1d=d.get("birthday_notify_1d", True),
        birthday_enabled=d.get("birthday_enabled", True),
        boost_enabled=d.get("boost_enabled", False),
        boost_percent=d.get("boost_percent", 7),
        boost_always=d.get("boost_always", False),
        boost_mode=d.get("boost_mode", "days"),
        boost_weekdays=d.get("boost_weekdays"),
        boost_dates=d.get("boost_dates"),
        silver_threshold=d.get("silver_threshold", 50000),
        gold_threshold=d.get("gold_threshold", 200000),
        cost_per_lead=d.get("cost_per_lead", 0),
        cost_per_client=d.get("cost_per_client", 0),
        tiers_json=d.get("tiers_json"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_settings(db: Session, tenant_id: int | None = None) -> Settings:
    """
    Настройки лояльности для тенанта. Для филиала возвращаются настройки
    корня сети — программа лояльности одна на всю сеть.
    """
    network_id = resolve_network_id(db, tenant_id)
    return get_or_create_settings(db, tenant_id=network_id)


def _clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(int(x), int(hi)))


def process_bonus_lifecycle(db: Session, user_id: int, now: datetime | None = None) -> None:
    """
    1) pending -> available (если available_from <= now)
    2) pending/available -> expired (если expires_at <= now) или remaining <= 0
    """
    now = now or _now()

    grants = db.scalars(
        select(BonusGrant).where(
            BonusGrant.user_id == user_id,
            BonusGrant.status == "pending",
            BonusGrant.available_from <= now,
            BonusGrant.remaining > 0,
        )
    ).all()
    for g in grants:
        g.status = "available"

    exp = db.scalars(
        select(BonusGrant).where(
            BonusGrant.user_id == user_id,
            BonusGrant.status.in_(["pending", "available"]),
            BonusGrant.expires_at <= now,
            BonusGrant.remaining > 0,
        )
    ).all()
    for g in exp:
        g.status = "expired"
        g.remaining = 0

    empty = db.scalars(
        select(BonusGrant).where(
            BonusGrant.user_id == user_id,
            BonusGrant.status.in_(["pending", "available"]),
            BonusGrant.remaining <= 0,
        )
    ).all()
    for g in empty:
        g.status = "expired"

    db.commit()


def get_balances(db: Session, user_id: int, now: datetime | None = None) -> dict:
    """
    Возвращает реальный баланс из BonusGrant (не кэш из User.bonus_balance).
    available — можно списать прямо сейчас
    pending   — начислены но ещё не активированы (activation_days не прошли)
    """
    now = now or _now()
    process_bonus_lifecycle(db, user_id=user_id, now=now)

    available = db.scalar(
        select(func.coalesce(func.sum(BonusGrant.remaining), 0)).where(
            BonusGrant.user_id == user_id,
            BonusGrant.status == "available",
            BonusGrant.expires_at > now,
            BonusGrant.remaining > 0,
        )
    )
    pending = db.scalar(
        select(func.coalesce(func.sum(BonusGrant.remaining), 0)).where(
            BonusGrant.user_id == user_id,
            BonusGrant.status == "pending",
            BonusGrant.remaining > 0,
        )
    )

    return {
        "available": int(available or 0),
        "pending": int(pending or 0),
        # total показывается клиенту в карточке (available + pending)
        "total": int(available or 0) + int(pending or 0),
    }


def consume_available(db: Session, user_id: int, to_spend: int, now: datetime | None = None) -> int:
    """
    Списывает бонусы из available-грантов.
    Гарантии:
      - никогда не спишет больше чем реально available (даже при race condition)
      - использует SELECT FOR UPDATE для row-level lock в PostgreSQL
      - списывает от ближайших к истечению (FIFO по expires_at)
    """
    now = now or _now()
    to_spend = int(to_spend or 0)
    if to_spend <= 0:
        return 0

    process_bonus_lifecycle(db, user_id=user_id, now=now)

    # SELECT FOR UPDATE — блокируем строки чтобы исключить race condition
    # при параллельных запросах (PostgreSQL row-level lock)
    grants = db.scalars(
        select(BonusGrant)
        .where(
            BonusGrant.user_id == user_id,
            BonusGrant.status == "available",
            BonusGrant.expires_at > now,
            BonusGrant.remaining > 0,
        )
        .order_by(BonusGrant.expires_at.asc(), BonusGrant.created_at.asc())
        .with_for_update()
    ).all()

    # Реальный доступный баланс — считаем из заблокированных строк
    real_available = sum(int(g.remaining) for g in grants)

    # Жёсткий лимит: не можем списать больше чем есть в грантах
    to_spend = min(to_spend, real_available)
    if to_spend <= 0:
        return 0

    spent = 0
    for g in grants:
        if to_spend <= 0:
            break
        take = min(int(g.remaining), to_spend)
        g.remaining = int(g.remaining) - take
        spent += take
        to_spend -= take
        if g.remaining <= 0:
            g.remaining = 0
            g.status = "expired"

    db.commit()
    return int(spent)


def calc_earn(paid_amount: int, tier: str, settings: Settings) -> int:
    """
    Логика начисления % бонусов:

    Если настроены Уровни (tiers_json не пуст):
      → % берётся из тира клиента (накопительный тир).
        Тир обновляется автоматически при каждой транзакции.
        Пример: клиент Silver → всегда 5% независимо от суммы чека.

    Если Уровни не настроены:
      → % определяется по сумме ТЕКУЩЕГО чека:
        чек >= gold_threshold  → earn_gold_percent
        чек >= silver_threshold → earn_silver_percent
        иначе                  → earn_bronze_percent
    """
    paid_amount = int(paid_amount or 0)
    if paid_amount <= 0:
        return 0

    tiers_cfg = getattr(settings, "tiers_json", None) or []

    if tiers_cfg:
        # ── Режим уровней: % из тира клиента ──────────────────
        tier = (tier or "Bronze").strip()
        tier_map = {
            t.get("name", ""): t.get("bonus_percent", 0)
            for t in tiers_cfg if isinstance(t, dict)
        }
        if tier in tier_map:
            # Тир клиента есть в настроенных уровнях — берём его %
            rate = int(tier_map[tier])
        else:
            # Тир клиента не в списке кастомных уровней → используем пороги по сумме чека
            silver_thr = int(getattr(settings, "silver_threshold", None) or 5000)
            gold_thr   = int(getattr(settings, "gold_threshold",   None) or 20000)
            if paid_amount >= gold_thr:
                rate = int(settings.earn_gold_percent)
            elif paid_amount >= silver_thr:
                rate = int(settings.earn_silver_percent)
            else:
                rate = int(settings.earn_bronze_percent)
    else:
        # ── Режим чека: % по сумме одного чека ────────────────
        silver_thr = int(getattr(settings, "silver_threshold", None) or 5000)
        gold_thr   = int(getattr(settings, "gold_threshold",   None) or 20000)
        if paid_amount >= gold_thr:
            rate = int(settings.earn_gold_percent)
        elif paid_amount >= silver_thr:
            rate = int(settings.earn_silver_percent)
        else:
            rate = int(settings.earn_bronze_percent)

    return int(paid_amount * rate // 100)


def redeem_cap(paid_amount: int, settings: Settings) -> int:
    paid_amount = int(paid_amount or 0)
    if paid_amount <= 0:
        return 0
    pct = _clamp_int(settings.redeem_max_percent, 0, 100)
    return int(paid_amount * pct // 100)


def grant_purchase_bonus(
    db: Session,
    user_id: int,
    earn: int,
    settings: Settings,
    txn_id: int | None = None,
    now: datetime | None = None,
    tenant_id: int | None = None,
) -> None:
    now = now or _now()
    earn = int(earn or 0)
    if earn <= 0:
        return

    activation_days = max(0, int(settings.activation_days or 0))
    # burn_days минимум 1 день — иначе бонус истекает в момент начисления
    burn_days = max(1, int(settings.burn_days or 365))

    available_from = now + timedelta(days=activation_days)
    # Срок жизни считается с момента активации (не начисления)
    expires_at = available_from + timedelta(days=burn_days)
    status = "available" if activation_days == 0 else "pending"

    g = BonusGrant(
        user_id=user_id,
        tenant_id=tenant_id,
        transaction_id=txn_id,
        amount=earn,
        remaining=earn,
        status=status,
        available_from=available_from,
        expires_at=expires_at,
        source="purchase",
    )
    db.add(g)
    db.commit()