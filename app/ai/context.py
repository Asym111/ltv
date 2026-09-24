# app/ai/context.py
"""
Богатый контекст для AI: всё, что нужно, чтобы советы были по делу, а не общими.

Раньше AI видел только 50 последних транзакций, сумму и баланс — и поэтому:
  - считал средний чек с нулевыми/возвращёнными чеками (занижал в разы);
  - предлагал «подарить 5 000» клиенту, у которого на балансе уже 258 000;
  - не знал правил программы (% начисления, лимит списания, сгорание, уровни);
  - не видел ритм покупок клиента и не мог сказать, «опаздывает» ли он.

Здесь собираются факты, посчитанные кодом (LLM плохо считает) — модель
только интерпретирует готовые цифры.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import decrypt_field
from app.models.bonus_grant import BonusGrant
from app.models.transaction import Transaction
from app.models.user import User

TIER_RU = {"Bronze": "Бронза", "Silver": "Серебро", "Gold": "Золото"}
GIFT_SOURCES = ("ai_grant", "manual", "bulk", "gift", "birthday", "welcome")


def _now() -> datetime:
    from app.services.loyalty_engine import _now as loyalty_now
    return loyalty_now()


def _money_tx(q):
    """Только реальные покупки: сумма > 0 и не полностью возвращённые."""
    return q.filter(Transaction.paid_amount > 0, Transaction.status != "refunded")


# ─────────────────────────────────────────────────────────────
# Правила программы лояльности
# ─────────────────────────────────────────────────────────────
def loyalty_rules(db: Session, tenant_id: int | None) -> dict[str, Any]:
    from app.services.loyalty_engine import get_settings
    s = get_settings(db, tenant_id=tenant_id)
    tiers = []
    for t in (getattr(s, "tiers_json", None) or []):
        if isinstance(t, dict):
            tiers.append({
                "name": t.get("name"),
                "spend_from": int(t.get("spend_from") or 0),
                "bonus_percent": t.get("bonus_percent"),
            })
    tiers.sort(key=lambda x: x["spend_from"])
    return {
        "bonus_name": getattr(s, "bonus_name", "бонусы"),
        "earn_percent": {
            "Bronze": int(s.earn_bronze_percent or 0),
            "Silver": int(s.earn_silver_percent or 0),
            "Gold": int(s.earn_gold_percent or 0),
        },
        "tiers_mode": "cumulative_spend" if tiers else "per_check",
        "tiers": tiers,
        "per_check_thresholds": None if tiers else {
            "silver_from_check": int(s.silver_threshold or 0),
            "gold_from_check": int(s.gold_threshold or 0),
        },
        "redeem_max_percent_of_check": int(s.redeem_max_percent or 0),
        "activation_days": int(s.activation_days or 0),
        "burn_days": int(s.burn_days or 0),
        "birthday_bonus": int(s.birthday_bonus_amount or 0) if bool(getattr(s, "birthday_enabled", True)) else 0,
        "tier_downgrade_after_days_inactive": 90,
    }


def _next_tier(rules: dict, tier: str | None, total_spent: int) -> dict | None:
    tiers = rules.get("tiers") or []
    if not tiers:
        return None
    for t in tiers:
        if int(t["spend_from"]) > total_spent:
            return {"name": t["name"], "spend_from": int(t["spend_from"]),
                    "left_to_spend": int(t["spend_from"]) - total_spent}
    return None


# ─────────────────────────────────────────────────────────────
# Клиент
# ─────────────────────────────────────────────────────────────
def network_benchmarks(db: Session, network_id: int) -> dict[str, Any]:
    """Средние по базе — чтобы AI сравнивал клиента с остальными."""
    base = _money_tx(
        db.query(Transaction).join(User, User.id == Transaction.user_id).filter(User.tenant_id == network_id)
    )
    cnt, total = base.with_entities(func.count(Transaction.id), func.coalesce(func.sum(Transaction.paid_amount), 0)).one()
    cnt, total = int(cnt or 0), int(total or 0)
    buyers = int(base.with_entities(func.count(func.distinct(Transaction.user_id))).scalar() or 0)
    return {
        "avg_check": round(total / cnt) if cnt else 0,
        "avg_purchases_per_client": round(cnt / buyers, 2) if buyers else 0,
        "avg_ltv": round(total / buyers) if buyers else 0,
    }


def client_context(db: Session, user: User, network_id: int, tenant_id: int | None) -> dict[str, Any]:
    now = _now()
    rules = loyalty_rules(db, tenant_id or network_id)

    all_tx = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.asc())
        .all()
    )
    buys = [t for t in all_tx if int(t.paid_amount or 0) > 0 and t.status != "refunded"]
    zero_tx = [t for t in all_tx if int(t.paid_amount or 0) <= 0]
    refunds = [t for t in all_tx if int(t.refunded_amount or 0) > 0]

    net = lambda t: int(t.paid_amount or 0) - int(t.refunded_amount or 0)  # noqa: E731
    total_spent = sum(net(t) for t in buys)
    n = len(buys)

    first_at = buys[0].created_at if buys else None
    last_at = buys[-1].created_at if buys else None
    recency = (now - last_at).days if last_at else None

    # Ритм: дни между покупками (покупки в один день считаем одним визитом)
    visit_days = sorted({t.created_at.date() for t in buys})
    gaps = [(b - a).days for a, b in zip(visit_days, visit_days[1:]) if (b - a).days > 0]
    cadence = round(median(gaps)) if gaps else None
    overdue = None
    expected_next = None
    if cadence and last_at:
        expected_next = (last_at + timedelta(days=cadence)).date().isoformat()
        overdue = recency - cadence if recency is not None else None

    branches = Counter(int(t.tenant_id) for t in buys)
    methods = Counter(str(t.payment_method or "OTHER") for t in buys)

    # Бонусы
    from app.services.loyalty_engine import get_balances
    bal = get_balances(db, user.id)
    in30 = now + timedelta(days=30)
    expiring = (
        db.query(func.coalesce(func.sum(BonusGrant.remaining), 0), func.min(BonusGrant.expires_at))
        .filter(
            BonusGrant.user_id == user.id,
            BonusGrant.status == "available",
            BonusGrant.remaining > 0,
            BonusGrant.expires_at > now,
            BonusGrant.expires_at <= in30,
        )
        .one()
    )
    earned_total = sum(int(t.earned_points or 0) for t in all_tx)
    redeemed_total = sum(int(t.redeem_points or 0) for t in all_tx)

    since90 = now - timedelta(days=90)
    gifts = (
        db.query(BonusGrant.source, BonusGrant.amount, BonusGrant.created_at)
        .filter(
            BonusGrant.user_id == user.id,
            BonusGrant.transaction_id.is_(None),
            BonusGrant.created_at >= since90,
        )
        .order_by(BonusGrant.created_at.desc())
        .limit(10)
        .all()
    )
    gifts_list = [
        {"source": g.source, "amount": int(g.amount or 0), "days_ago": (now - g.created_at).days}
        for g in gifts
    ]
    gifted_30d = sum(g["amount"] for g in gifts_list if g["days_ago"] <= 30)

    # День рождения
    bday_in = None
    if user.birth_date:
        try:
            bd = user.birth_date.replace(year=now.year)
        except ValueError:  # 29 февраля
            bd = user.birth_date.replace(year=now.year, day=28)
        if bd < now.date():
            try:
                bd = bd.replace(year=now.year + 1)
            except ValueError:
                bd = bd.replace(year=now.year + 1, day=28)
        bday_in = (bd - now.date()).days

    avg_check = round(total_spent / n) if n else 0
    earn_pct = rules["earn_percent"].get(user.tier or "Bronze", 0)
    if rules.get("tiers"):
        for t in rules["tiers"]:
            if t.get("name") == user.tier and t.get("bonus_percent") is not None:
                earn_pct = t["bonus_percent"]

    return {
        "client": {
            "name": decrypt_field(user.full_name) if user.full_name else None,
            "tier": user.tier,
            "tier_ru": TIER_RU.get(user.tier or "", user.tier),
            "earn_percent_now": earn_pct,
            "client_since": (user.created_at.date().isoformat() if user.created_at else None),
            "whatsapp_opt_out": bool(getattr(user, "wa_opt_out", False)),
            "birthday_in_days": bday_in,
        },
        "purchases": {
            "count": n,
            "total_spent_net": total_spent,
            "avg_check": avg_check,
            "max_check": max((net(t) for t in buys), default=0),
            "first_purchase": first_at.date().isoformat() if first_at else None,
            "last_purchase": last_at.date().isoformat() if last_at else None,
            "recency_days": recency,
            "visits": len(visit_days),
            "typical_gap_days": cadence,
            "expected_next_visit": expected_next,
            "days_overdue_vs_own_rhythm": overdue,
            "zero_amount_records": len(zero_tx),
            "refunds_count": len(refunds),
            "refunded_amount": sum(int(t.refunded_amount or 0) for t in refunds),
            "branches_share": {str(k): v for k, v in branches.most_common()},
            "payment_methods": dict(methods.most_common()),
            "last_5": [
                {"date": t.created_at.date().isoformat(), "paid": net(t),
                 "redeemed": int(t.redeem_points or 0), "earned": int(t.earned_points or 0),
                 "status": t.status}
                for t in reversed(buys[-5:])
            ],
        },
        "bonuses": {
            "available": int(bal.get("available") or 0),
            "pending": int(bal.get("pending") or 0),
            "expiring_30d": int(expiring[0] or 0),
            "nearest_expiry": expiring[1].date().isoformat() if expiring[1] else None,
            "earned_total": earned_total,
            "redeemed_total": redeemed_total,
            "redemption_rate": round(redeemed_total / earned_total, 2) if earned_total else None,
            "balance_vs_avg_check": round(int(bal.get("available") or 0) / avg_check, 2) if avg_check else None,
            "max_redeem_on_avg_check": int(avg_check * rules["redeem_max_percent_of_check"] / 100) if avg_check else 0,
            "gifts_last_90d": gifts_list,
            "gifted_last_30d": gifted_30d,
        },
        "next_tier": _next_tier(rules, user.tier, total_spent),
        "loyalty_rules": rules,
        "network_benchmarks": network_benchmarks(db, network_id),
    }


# ─────────────────────────────────────────────────────────────
# Бизнес
# ─────────────────────────────────────────────────────────────
def business_extras(db: Session, network_id: int, tenant_ids: list[int]) -> dict[str, Any]:
    """Дополнение к обзору бизнеса: экономика бонусов, филиалы, повторные покупки, клиенты под угрозой."""
    from app.models.auth import Tenant

    now = _now()
    d30 = now - timedelta(days=30)

    # Экономика бонусов
    live = (
        db.query(BonusGrant.status, func.coalesce(func.sum(BonusGrant.remaining), 0))
        .join(User, User.id == BonusGrant.user_id)
        .filter(User.tenant_id == network_id, BonusGrant.remaining > 0, BonusGrant.expires_at > now)
        .group_by(BonusGrant.status)
        .all()
    )
    live_map = {str(s): int(v or 0) for s, v in live}
    expiring_30d = int(
        db.query(func.coalesce(func.sum(BonusGrant.remaining), 0))
        .join(User, User.id == BonusGrant.user_id)
        .filter(User.tenant_id == network_id, BonusGrant.status == "available",
                BonusGrant.remaining > 0, BonusGrant.expires_at > now,
                BonusGrant.expires_at <= now + timedelta(days=30))
        .scalar() or 0
    )
    tx30 = _money_tx(db.query(Transaction).filter(Transaction.tenant_id.in_(tenant_ids), Transaction.created_at >= d30))
    earned30, redeemed30, paid30 = tx30.with_entities(
        func.coalesce(func.sum(Transaction.earned_points), 0),
        func.coalesce(func.sum(Transaction.redeem_points), 0),
        func.coalesce(func.sum(Transaction.paid_amount), 0),
    ).one()

    # Филиалы
    names = {int(t.id): t.name for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()}
    by_branch = (
        tx30.with_entities(Transaction.tenant_id, func.count(Transaction.id), func.coalesce(func.sum(Transaction.paid_amount), 0))
        .group_by(Transaction.tenant_id).all()
    )
    branches = [
        {"branch": names.get(int(tid), str(tid)), "checks_30d": int(c), "revenue_30d": int(r),
         "avg_check": round(int(r) / int(c)) if c else 0}
        for tid, c, r in by_branch
    ]

    # Повторные покупки
    per_user = (
        _money_tx(db.query(Transaction.user_id, func.count(Transaction.id).label("c"),
                           func.coalesce(func.sum(Transaction.paid_amount), 0).label("s"),
                           func.max(Transaction.created_at).label("last"))
                  .filter(Transaction.tenant_id.in_(tenant_ids)))
        .group_by(Transaction.user_id).all()
    )
    buyers = len(per_user)
    repeat = sum(1 for r in per_user if int(r.c) >= 2)

    # Ценные клиенты, которые пропадают: верхние 20% по сумме, не были 45+ дней
    at_risk = []
    if per_user:
        top = sorted(per_user, key=lambda r: int(r.s), reverse=True)[:max(1, buyers // 5)]
        lost = [r for r in top if r.last and (now - r.last).days >= 45]
        lost.sort(key=lambda r: int(r.s), reverse=True)
        ids = [r.user_id for r in lost[:10]]
        umap = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
        for r in lost[:10]:
            u = umap.get(r.user_id)
            if not u:
                continue
            at_risk.append({
                "phone": decrypt_field(u.phone) or u.phone,
                "tier": u.tier,
                "total_spent": int(r.s),
                "purchases": int(r.c),
                "days_since_last": (now - r.last).days,
            })
        at_risk_total = len(lost)
    else:
        at_risk_total = 0

    opt_out = int(db.query(func.count(User.id)).filter(User.tenant_id == network_id, User.wa_opt_out.is_(True)).scalar() or 0)

    wa_credits_balance = None
    try:
        from app.services.wa_credits import get_balance
        wa_credits_balance = get_balance(db, network_id)
    except Exception:
        pass

    return {
        "loyalty_rules": loyalty_rules(db, network_id),
        "bonus_economy": {
            "liability_available": live_map.get("available", 0),
            "liability_pending": live_map.get("pending", 0),
            "expiring_next_30d": expiring_30d,
            "earned_30d": int(earned30 or 0),
            "redeemed_30d": int(redeemed30 or 0),
            "redeem_share_of_revenue_30d_pct": round(int(redeemed30 or 0) / int(paid30) * 100, 1) if paid30 else 0,
        },
        "branches_30d": branches,
        "repeat_purchase": {
            "buyers": buyers,
            "repeat_buyers": repeat,
            "repeat_rate_pct": round(repeat / buyers * 100, 1) if buyers else 0,
        },
        "valuable_at_risk": {"count": at_risk_total, "top": at_risk},
        "whatsapp": {"opt_out_clients": opt_out, "broadcast_credits": wa_credits_balance},
        "today": now.date().isoformat(),
    }
