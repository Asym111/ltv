# app/ai/insights.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.user import User
from app.models.transaction import Transaction


@dataclass(frozen=True)
class OverviewNumbers:
    clients: int
    active_30d: int
    churn_risk: int
    total_revenue_30d: int
    avg_check_30d: float


def _utcnow() -> datetime:
    return datetime.utcnow()


def calc_overview_numbers(db: Session, now: datetime | None = None) -> OverviewNumbers:
    now = now or _utcnow()
    since_30d = now - timedelta(days=30)

    clients = int(db.query(func.count(User.id)).scalar() or 0)

    # Последняя покупка по клиентам
    subq_last = (
        db.query(
            Transaction.user_id.label("user_id"),
            func.max(Transaction.created_at).label("last_tx"),
        )
        .group_by(Transaction.user_id)
        .subquery()
    )

    active_30d = int(
        db.query(func.count(subq_last.c.user_id))
        .filter(subq_last.c.last_tx >= since_30d)
        .scalar()
        or 0
    )

    # churn_risk: не покупали 30+ дней (и вообще имеют хотя бы 1 транзакцию)
    churn_risk = int(
        db.query(func.count(subq_last.c.user_id))
        .filter(subq_last.c.last_tx < since_30d)
        .scalar()
        or 0
    )

    # Выручка и средний чек за 30 дней
    total_revenue_30d = int(
        db.query(func.coalesce(func.sum(Transaction.paid_amount), 0))
        .filter(Transaction.created_at >= since_30d)
        .scalar()
        or 0
    )
    count_30d = int(
        db.query(func.count(Transaction.id))
        .filter(Transaction.created_at >= since_30d)
        .scalar()
        or 0
    )
    avg_check_30d = float(total_revenue_30d / count_30d) if count_30d else 0.0

    return OverviewNumbers(
        clients=clients,
        active_30d=active_30d,
        churn_risk=churn_risk,
        total_revenue_30d=total_revenue_30d,
        avg_check_30d=round(avg_check_30d, 2),
    )


def calc_top_clients_share(db: Session, now: datetime | None = None) -> dict[str, Any]:
    """
    20/80 анализ по total paid_amount.
    Возвращаем долю выручки топ-20% клиентов.
    """
    # total spent per user
    rows = (
        db.query(
            Transaction.user_id,
            func.coalesce(func.sum(Transaction.paid_amount), 0).label("spent"),
        )
        .group_by(Transaction.user_id)
        .all()
    )
    if not rows:
        return {"top_20_share": 0.0, "users_with_tx": 0, "total_spent": 0}

    spent_list = sorted([int(r.spent or 0) for r in rows], reverse=True)
    total = sum(spent_list)
    n = len(spent_list)
    top_n = max(1, int(round(n * 0.2)))
    top_sum = sum(spent_list[:top_n])

    share = (top_sum / total) if total else 0.0
    return {
        "top_20_share": round(float(share), 4),
        "users_with_tx": n,
        "total_spent": total,
        "top_n": top_n,
    }


def build_overview_payload(db: Session) -> dict[str, Any]:
    nums = calc_overview_numbers(db)
    pareto = calc_top_clients_share(db)

    return {
        "summary": {
            "clients": nums.clients,
            "active_30d": nums.active_30d,
            "churn_risk": nums.churn_risk,
            "total_revenue_30d": nums.total_revenue_30d,
            "avg_check_30d": nums.avg_check_30d,
        },
        "pareto": pareto,
    }
