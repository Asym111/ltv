from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.settings_model import Settings
from app.models.bonus_grant import BonusGrant


def _now() -> datetime:
    return datetime.utcnow()


def get_settings(db: Session) -> Settings:
    s = db.scalar(select(Settings).order_by(Settings.id.asc()).limit(1))
    if s:
        return s
    s = Settings()
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


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
    paid_amount = int(paid_amount or 0)
    if paid_amount <= 0:
        return 0

    tier = (tier or "Bronze").strip()
    if tier == "Gold":
        rate = int(settings.earn_gold_percent)
    elif tier == "Silver":
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