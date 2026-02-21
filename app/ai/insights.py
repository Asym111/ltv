# app/ai/insights.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.user import User


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
        .scalar() or 0
    )

    churn_risk = int(
        db.query(func.count(subq_last.c.user_id))
        .filter(subq_last.c.last_tx < since_30d)
        .scalar() or 0
    )

    total_revenue_30d = int(
        db.query(func.coalesce(func.sum(Transaction.paid_amount), 0))
        .filter(Transaction.created_at >= since_30d)
        .scalar() or 0
    )

    count_30d = int(
        db.query(func.count(Transaction.id))
        .filter(Transaction.created_at >= since_30d)
        .scalar() or 0
    )

    avg_check_30d = round(float(total_revenue_30d / count_30d), 2) if count_30d else 0.0

    return OverviewNumbers(
        clients=clients,
        active_30d=active_30d,
        churn_risk=churn_risk,
        total_revenue_30d=total_revenue_30d,
        avg_check_30d=avg_check_30d,
    )


def calc_top_clients_share(db: Session) -> dict[str, Any]:
    rows = (
        db.query(
            Transaction.user_id,
            func.coalesce(func.sum(Transaction.paid_amount), 0).label("spent"),
        )
        .group_by(Transaction.user_id)
        .all()
    )
    if not rows:
        return {"top_20_share": 0.0, "users_with_tx": 0, "total_spent": 0, "top_n": 0}

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


def _jsonable(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonable(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def build_overview_payload(db: Session, tenant_id: int | None = None) -> dict[str, Any]:
    """
    Расширенный payload для AI:
    - тренды выручки (7д / 30д / vs предыдущий 30д)
    - tier distribution (Bronze/Silver/Gold)
    - новые клиенты за 30д и 7д
    - avg_recency (средние дни с последней покупки)
    - топ-5 клиентов по выручке
    - pareto 80/20
    - tenant_id изоляция данных
    """
    now = _utcnow()
    since_30d = now - timedelta(days=30)
    since_7d  = now - timedelta(days=7)
    since_60d = now - timedelta(days=60)

    def _txq():
        q = db.query(Transaction)
        if tenant_id:
            q = q.filter(Transaction.tenant_id == tenant_id)
        return q

    def _userq():
        q = db.query(User)
        if tenant_id:
            q = q.filter(User.tenant_id == tenant_id)
        return q

    # ── Кол-во клиентов ──────────────────────────────────────
    clients = int(_userq().with_entities(func.count(User.id)).scalar() or 0)

    subq_last = (
        _txq()
        .with_entities(
            Transaction.user_id.label("user_id"),
            func.max(Transaction.created_at).label("last_tx"),
        )
        .group_by(Transaction.user_id)
        .subquery()
    )

    active_30d = int(
        db.query(func.count(subq_last.c.user_id))
        .filter(subq_last.c.last_tx >= since_30d)
        .scalar() or 0
    )
    churn_risk = int(
        db.query(func.count(subq_last.c.user_id))
        .filter(subq_last.c.last_tx < since_30d)
        .scalar() or 0
    )

    # ── Выручка с трендом ────────────────────────────────────
    revenue_30d = int(
        _txq()
        .with_entities(func.coalesce(func.sum(Transaction.paid_amount), 0))
        .filter(Transaction.created_at >= since_30d, Transaction.status == "completed")
        .scalar() or 0
    )
    revenue_7d = int(
        _txq()
        .with_entities(func.coalesce(func.sum(Transaction.paid_amount), 0))
        .filter(Transaction.created_at >= since_7d, Transaction.status == "completed")
        .scalar() or 0
    )
    # Предыдущий период 30д — для расчёта тренда
    revenue_prev_30d = int(
        _txq()
        .with_entities(func.coalesce(func.sum(Transaction.paid_amount), 0))
        .filter(
            Transaction.created_at >= since_60d,
            Transaction.created_at < since_30d,
            Transaction.status == "completed",
        )
        .scalar() or 0
    )
    revenue_trend_pct = 0.0
    if revenue_prev_30d > 0:
        revenue_trend_pct = round(
            (revenue_30d - revenue_prev_30d) / revenue_prev_30d * 100, 1
        )

    count_30d = int(
        _txq()
        .with_entities(func.count(Transaction.id))
        .filter(Transaction.created_at >= since_30d)
        .scalar() or 0
    )
    avg_check_30d = round(revenue_30d / count_30d, 0) if count_30d else 0.0

    # ── Новые клиенты ────────────────────────────────────────
    new_clients_30d = int(
        _userq()
        .with_entities(func.count(User.id))
        .filter(User.created_at >= since_30d)
        .scalar() or 0
    )
    new_clients_7d = int(
        _userq()
        .with_entities(func.count(User.id))
        .filter(User.created_at >= since_7d)
        .scalar() or 0
    )

    # ── Tier distribution ────────────────────────────────────
    tier_rows = (
        _userq()
        .with_entities(User.tier, func.count(User.id).label("cnt"))
        .group_by(User.tier)
        .all()
    )
    tier_dist = {str(r.tier or "Bronze"): int(r.cnt) for r in tier_rows}

    # ── Avg recency (средние дни с последней покупки) ────────
    avg_recency: float | None = None
    try:
        recency_rows = (
            db.query(subq_last.c.last_tx)
            .filter(subq_last.c.last_tx.isnot(None))
            .all()
        )
        if recency_rows:
            days_list = [(now - r[0]).days for r in recency_rows if r[0]]
            avg_recency = round(sum(days_list) / len(days_list), 1) if days_list else None
    except Exception:
        pass

    # ── Топ-5 клиентов по выручке ────────────────────────────
    top5: list[dict] = []
    try:
        top_rows = (
            _txq()
            .with_entities(
                Transaction.user_id,
                func.coalesce(func.sum(Transaction.paid_amount), 0).label("spent"),
                func.count(Transaction.id).label("txn_count"),
            )
            .filter(Transaction.status == "completed")
            .group_by(Transaction.user_id)
            .order_by(func.sum(Transaction.paid_amount).desc())
            .limit(5)
            .all()
        )
        user_ids = [r.user_id for r in top_rows]
        users_map = {}
        if user_ids:
            urows = _userq().filter(User.id.in_(user_ids)).all()
            users_map = {u.id: u for u in urows}

        for r in top_rows:
            u = users_map.get(r.user_id)
            top5.append({
                "phone": u.phone if u else str(r.user_id),
                "tier": u.tier if u else "?",
                "total_spent": int(r.spent),
                "txn_count": int(r.txn_count),
            })
    except Exception:
        pass

    pareto = calc_top_clients_share(db)

    payload: dict[str, Any] = {
        "summary": {
            "clients":           clients,
            "active_30d":        active_30d,
            "inactive_pct":      round((clients - active_30d) / clients * 100, 1) if clients else 0,
            "churn_risk":        churn_risk,
            "new_clients_30d":   new_clients_30d,
            "new_clients_7d":    new_clients_7d,
            "total_revenue_30d": revenue_30d,
            "total_revenue_7d":  revenue_7d,
            "revenue_trend_pct": revenue_trend_pct,
            "avg_check_30d":     avg_check_30d,
            "txn_count_30d":     count_30d,
            "avg_recency_days":  avg_recency,
        },
        "tier_distribution": tier_dist,
        "top_clients": top5,
        "pareto": pareto,
        "nav_whitelist": {
            "analytics":       "nav:/admin/analytics",
            "campaigns":       "nav:/admin/campaigns",
            "transactions":    "nav:/admin/transactions",
            "clients":         "nav:/admin/clients",
            "settings":        "nav:/admin/settings",
            "accounts":        "nav:/admin/accounts",
            "client_card":     "nav:/admin/client/{phone}",
            "segment":         "nav:/admin/analytics/segment/{key}",
            "campaign_detail": "nav:/admin/campaigns/{id}",
        },
        "campaign_prefill_hint": (
            "Для создания кампании: "
            "nav:/admin/campaigns?create=1&name=...&segment_key=vip&bonus=5000&build=1"
        ),
        "grant_bonus_hint": (
            "Для начисления бонусов клиенту: "
            "action:grant_bonus|phone=7XXXXXXXXXX|amount=N|reason=текст"
        ),
    }

    # Расширенная аналитика если сервис доступен
    try:
        from app.services.analytics import build_analytics_overview  # type: ignore
        ov = build_analytics_overview(db)
        payload["analytics_overview"] = _jsonable(ov)

        segments: list[dict] = []
        if isinstance(ov, dict):
            for s in (ov.get("segments") or [])[:20]:
                if isinstance(s, dict):
                    key = str(s.get("key") or "").strip()
                    title = str(s.get("title") or "").strip()
                    count = s.get("count") or s.get("clients_count")
                    if key:
                        segments.append({"key": key, "title": title, "count": count})
        payload["segments_allowed"] = segments
    except Exception as e:
        payload["analytics_overview_error"] = str(e)
        # Базовые сегменты с реальными данными
        payload["segments_allowed"] = [
            {"key": "vip",    "title": "VIP клиенты",     "count": tier_dist.get("Gold", 0)},
            {"key": "active", "title": "Активные",         "count": active_30d},
            {"key": "risk",   "title": "Риск оттока",      "count": churn_risk},
            {"key": "lost",   "title": "Потерянные",       "count": max(0, clients - active_30d - new_clients_30d)},
            {"key": "new",    "title": "Новые за 30 дней", "count": new_clients_30d},
        ]

    return payload