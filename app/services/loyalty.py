from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.loyalty_rules import RULES
from app.models.user import User
from app.models.transaction import Transaction
from app.models.bonus import BonusGrant


def _now() -> datetime:
    return datetime.utcnow()


def _q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_rate_by_tier(tier: str) -> Decimal:
    tier = (tier or "").strip().lower()
    if tier == "gold":
        return RULES.gold_rate
    if tier == "silver":
        return RULES.silver_rate
    return RULES.bronze_rate


def calc_accrual(amount: Decimal, tier: str) -> Decimal:
    if amount <= 0:
        return Decimal("0.00")
    return _q2(amount * get_rate_by_tier(tier))


def calc_redeem_cap(amount: Decimal) -> Decimal:
    if amount <= 0:
        return Decimal("0.00")
    return _q2(amount * RULES.max_redeem_percent)


def process_bonus_lifecycle(db: Session, now: datetime | None = None) -> None:
    now = now or _now()

    # pending -> available
    grants_to_activate = db.scalars(
        select(BonusGrant).where(
            BonusGrant.status == "pending",
            BonusGrant.available_from <= now,
            BonusGrant.remaining > 0,
        )
    ).all()
    for g in grants_to_activate:
        g.status = "available"

    # expire
    grants_to_expire = db.scalars(
        select(BonusGrant).where(
            BonusGrant.status.in_(["pending", "available"]),
            BonusGrant.expires_at <= now,
            BonusGrant.remaining > 0,
        )
    ).all()
    for g in grants_to_expire:
        g.status = "expired"
        g.remaining = Decimal("0.00")

    # empty -> expired
    empty_grants = db.scalars(
        select(BonusGrant).where(
            BonusGrant.status.in_(["pending", "available"]),
            BonusGrant.remaining <= 0,
        )
    ).all()
    for g in empty_grants:
        g.status = "expired"

    db.commit()


def get_bonus_balances(db: Session, user_id: int, now: datetime | None = None) -> dict:
    now = now or _now()
    process_bonus_lifecycle(db, now=now)

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
    expiring_soon = db.scalar(
        select(func.coalesce(func.sum(BonusGrant.remaining), 0)).where(
            BonusGrant.user_id == user_id,
            BonusGrant.status == "available",
            BonusGrant.expires_at <= now + timedelta(days=14),
            BonusGrant.expires_at > now,
            BonusGrant.remaining > 0,
        )
    )

    return {
        "available": Decimal(str(available or 0)),
        "pending": Decimal(str(pending or 0)),
        "expiring_soon": Decimal(str(expiring_soon or 0)),
    }


def calc_tier_by_total_spent(total_spent: Decimal) -> str:
    if total_spent >= RULES.gold_threshold:
        return "Gold"
    if total_spent >= RULES.silver_threshold:
        return "Silver"
    return "Bronze"


def _consume_available_bonuses(db: Session, user_id: int, to_spend: Decimal, now: datetime) -> Decimal:
    if to_spend <= 0:
        return Decimal("0.00")

    process_bonus_lifecycle(db, now=now)

    grants = db.scalars(
        select(BonusGrant)
        .where(
            BonusGrant.user_id == user_id,
            BonusGrant.status == "available",
            BonusGrant.expires_at > now,
            BonusGrant.remaining > 0,
        )
        .order_by(BonusGrant.expires_at.asc(), BonusGrant.created_at.asc())
    ).all()

    spent = Decimal("0.00")
    for g in grants:
        if to_spend <= 0:
            break

        rem = Decimal(str(g.remaining))
        take = min(rem, to_spend)

        g.remaining = _q2(rem - take)

        spent = _q2(spent + take)
        to_spend = _q2(to_spend - take)

    db.commit()
    return spent


def create_purchase_transaction(
    db: Session,
    user: User,
    amount: Decimal,
    currency: str = "KZT",
    requested_redeem: Decimal = Decimal("0.00"),
    now: datetime | None = None,
) -> Transaction:
    now = now or _now()
    if amount <= 0:
        raise ValueError("amount must be > 0")

    balances = get_bonus_balances(db, user_id=user.id, now=now)
    available_balance = balances["available"]

    cap = calc_redeem_cap(amount)
    requested_redeem = _q2(requested_redeem)
    redeem_target = min(requested_redeem, cap, available_balance)
    redeem_target = _q2(max(redeem_target, Decimal("0.00")))

    redeem_used = _consume_available_bonuses(db, user_id=user.id, to_spend=redeem_target, now=now)

    net_amount = _q2(amount - redeem_used)
    earned = calc_accrual(net_amount, user.loyalty_tier)

    tx = Transaction(
        user_id=user.id,
        amount=float(_q2(amount)),
        currency=(currency or "KZT").upper(),
        redeem_bonus=float(redeem_used),
        net_amount=float(net_amount),
        earned_bonus=float(earned),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    if earned > 0:
        available_from = now + timedelta(days=int(RULES.activation_days))
        expires_at = available_from + timedelta(days=int(RULES.burn_days))
        status = "available" if RULES.activation_days == 0 else "pending"

        grant = BonusGrant(
            user_id=user.id,
            amount=float(earned),
            remaining=float(earned),
            status=status,
            available_from=available_from,
            expires_at=expires_at,
            source="purchase",
        )
        db.add(grant)
        db.commit()

    return tx


def grant_birthday_bonus(db: Session, user: User, now: datetime | None = None) -> BonusGrant | None:
    now = now or _now()
    if not user.birth_date:
        return None

    today = now.date()
    if (user.birth_date.month, user.birth_date.day) != (today.month, today.day):
        return None

    source = f"birthday:{today.year}"
    exists = db.scalar(
        select(func.count()).select_from(BonusGrant).where(
            BonusGrant.user_id == user.id,
            BonusGrant.source == source,
        )
    )
    if (exists or 0) > 0:
        return None

    amount = _q2(RULES.birthday_bonus)
    if amount <= 0:
        return None

    available_from = now
    expires_at = now + timedelta(days=int(RULES.birthday_ttl_days))

    grant = BonusGrant(
        user_id=user.id,
        amount=float(amount),
        remaining=float(amount),
        status="available",
        available_from=available_from,
        expires_at=expires_at,
        source=source,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant
