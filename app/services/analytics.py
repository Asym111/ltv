# app/services/analytics.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.models.user import User
from app.models.transaction import Transaction


@dataclass
class _ClientAgg:
    phone: str
    full_name: Optional[str]
    tier: str

    last_tx_at: Optional[datetime]

    tx_total: int
    spent_total: int

    tx_90d: int
    spent_90d: int

    recency_days: int


def _utcnow() -> datetime:
    return datetime.utcnow()


def _quantile_cutoffs(values: List[int], qs: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
    arr = sorted(values)
    n = len(arr)

    def at(q: float) -> int:
        if n == 1:
            return arr[0]
        idx = int(round((n - 1) * q))
        idx = max(0, min(n - 1, idx))
        return arr[idx]

    return (at(qs[0]), at(qs[1]), at(qs[2]), at(qs[3]))


def _score_1_5_by_cutoffs(v: int, c20: int, c40: int, c60: int, c80: int) -> int:
    if v <= c20:
        return 1
    if v <= c40:
        return 2
    if v <= c60:
        return 3
    if v <= c80:
        return 4
    return 5


def _score_1_5_inverse_by_cutoffs(v: int, c20: int, c40: int, c60: int, c80: int) -> int:
    # Recency: меньше = лучше
    if v <= c20:
        return 5
    if v <= c40:
        return 4
    if v <= c60:
        return 3
    if v <= c80:
        return 2
    return 1


def _load_clients_agg(db: Session) -> List[_ClientAgg]:
    now = _utcnow()
    since_90 = now - timedelta(days=90)

    q = (
        db.query(
            User.phone,
            User.full_name,
            User.tier,
            func.max(Transaction.created_at).label("last_tx_at"),
            func.coalesce(func.count(Transaction.id), 0).label("tx_total"),
            func.coalesce(func.sum(Transaction.paid_amount), 0).label("spent_total"),
            func.coalesce(
                func.sum(case((Transaction.created_at >= since_90, Transaction.paid_amount), else_=0)),
                0,
            ).label("spent_90d"),
            func.coalesce(
                func.sum(case((Transaction.created_at >= since_90, 1), else_=0)),
                0,
            ).label("tx_90d"),
        )
        .outerjoin(Transaction, Transaction.user_id == User.id)
        .group_by(User.id)
    )

    out: List[_ClientAgg] = []
    for phone, full_name, tier, last_tx_at, tx_total, spent_total, spent_90d, tx_90d in q.all():
        if not phone:
            continue

        last_dt: Optional[datetime] = last_tx_at
        if last_dt:
            rec = max(0, int((now - last_dt).total_seconds() // 86400))
        else:
            rec = 99999  # никогда не покупал

        out.append(
            _ClientAgg(
                phone=str(phone),
                full_name=(full_name or None),
                tier=str(tier or "Bronze"),
                last_tx_at=last_dt,
                tx_total=int(tx_total or 0),
                spent_total=int(spent_total or 0),
                tx_90d=int(tx_90d or 0),
                spent_90d=int(spent_90d or 0),
                recency_days=rec,
            )
        )

    return out


def build_analytics_overview(db: Session) -> Dict:
    now = _utcnow()

    def window(days: int) -> Dict:
        since = now - timedelta(days=days)

        revenue, tx_count, clients = (
            db.query(
                func.coalesce(func.sum(Transaction.paid_amount), 0),
                func.count(Transaction.id),
                func.count(func.distinct(Transaction.user_id)),
            )
            .filter(Transaction.created_at >= since)
            .first()
        )

        revenue_i = int(revenue or 0)
        tx_i = int(tx_count or 0)
        clients_i = int(clients or 0)
        avg = (revenue_i / tx_i) if tx_i else 0.0

        return {
            "days": days,
            "label": f"{days} дней",
            "revenue": revenue_i,
            "transactions": tx_i,
            "clients": clients_i,
            "avg_check": round(float(avg), 2),
        }

    windows = [window(7), window(30), window(90)]

    agg = _load_clients_agg(db)
    buyers = [c for c in agg if c.tx_total > 0]

    # VIP top-10% по total revenue
    vip_set = set()
    if buyers:
        sorted_by_spent = sorted(buyers, key=lambda x: x.spent_total, reverse=True)
        cut = max(1, int(len(sorted_by_spent) * 0.10))
        vip_set = set(x.phone for x in sorted_by_spent[:cut])

    seg_counts = {"new": 0, "active": 0, "sleeping": 0, "risk": 0, "lost": 0, "vip": 0}

    for c in agg:
        if c.phone in vip_set:
            seg_counts["vip"] += 1

        if c.tx_total == 0:
            seg_counts["lost"] += 1
            continue

        if c.tx_total == 1 and c.recency_days <= 7:
            seg_counts["new"] += 1
        elif c.recency_days <= 30:
            seg_counts["active"] += 1
        elif c.recency_days <= 90:
            seg_counts["sleeping"] += 1
        elif c.recency_days <= 180:
            seg_counts["risk"] += 1
        else:
            seg_counts["lost"] += 1

    segments = [
        {"key": "new", "title": "Новые", "hint": "1 покупка, ≤ 7 дней", "clients": seg_counts["new"]},
        {"key": "active", "title": "Активные", "hint": "последняя покупка ≤ 30 дней", "clients": seg_counts["active"]},
        {"key": "sleeping", "title": "Спящие", "hint": "31–90 дней без покупок", "clients": seg_counts["sleeping"]},
        {"key": "risk", "title": "В зоне риска", "hint": "91–180 дней без покупок", "clients": seg_counts["risk"]},
        {"key": "lost", "title": "Потерянные", "hint": "> 180 дней без покупок / нет покупок", "clients": seg_counts["lost"]},
        {"key": "vip", "title": "VIP", "hint": "топ 10% по сумме paid_amount", "clients": seg_counts["vip"]},
    ]

    # alerts (быстрые действия)
    alerts = [
        {
            "key": "alert_new",
            "title": "Новые клиенты",
            "level": "info",
            "count": seg_counts["new"],
            "hint": "сделать приветственный оффер",
            "href": "/admin/analytics/segment/new",
        },
        {
            "key": "alert_sleeping",
            "title": "Спящие",
            "level": "warning",
            "count": seg_counts["sleeping"],
            "hint": "реактивация (мягкий бонус/подборка)",
            "href": "/admin/analytics/segment/sleeping",
        },
        {
            "key": "alert_risk",
            "title": "В зоне риска",
            "level": "danger",
            "count": seg_counts["risk"],
            "hint": "срочно: персональный оффер / звонок",
            "href": "/admin/analytics/segment/risk",
        },
        {
            "key": "alert_lost",
            "title": "Потерянные",
            "level": "danger",
            "count": seg_counts["lost"],
            "hint": "кампания “вернуть клиента”",
            "href": "/admin/analytics/segment/lost",
        },
        {
            "key": "alert_vip",
            "title": "VIP",
            "level": "info",
            "count": seg_counts["vip"],
            "hint": "персональный сервис / early access",
            "href": "/admin/analytics/segment/vip",
        },
    ]

    total_clients = len(agg)
    users_with_tx = len(buyers)
    total_spent = int(sum(c.spent_total for c in buyers))

    return {
        "generated_at": now,
        "windows": windows,
        "segments": segments,
        "alerts": alerts,
        "clients_total": total_clients,
        "users_with_tx": users_with_tx,
        "total_spent": total_spent,
    }


def list_clients_by_segment(
    db: Session,
    key: str,
    limit: int = 200,
    offset: int = 0,
    r_min: int | None = None,
    f_min: int | None = None,
    m_min: int | None = None,
    q: str | None = None,
    sort: str | None = None,
) -> Dict:
    now = _utcnow()
    agg = _load_clients_agg(db)
    buyers = [c for c in agg if c.tx_total > 0]

    # VIP top-10% по total revenue
    vip_set = set()
    if buyers:
        sorted_by_spent = sorted(buyers, key=lambda x: x.spent_total, reverse=True)
        cut = max(1, int(len(sorted_by_spent) * 0.10))
        vip_set = set(x.phone for x in sorted_by_spent[:cut])

    def in_segment(c: _ClientAgg) -> bool:
        if key == "vip":
            return c.phone in vip_set
        if key == "new":
            return c.tx_total == 1 and c.recency_days <= 7
        if key == "active":
            return c.tx_total > 0 and c.recency_days <= 30
        if key == "sleeping":
            return c.tx_total > 0 and 31 <= c.recency_days <= 90
        if key == "risk":
            return c.tx_total > 0 and 91 <= c.recency_days <= 180
        if key == "lost":
            return c.tx_total == 0 or c.recency_days > 180
        return False

    selected = [c for c in agg if in_segment(c)]

    # --- RFM скоринг (1–5)
    f_vals = [c.tx_90d for c in buyers] or [0]
    m_vals = [c.spent_90d for c in buyers] or [0]
    r_vals = [c.recency_days for c in buyers] or [99999]

    use_quantiles = len(buyers) >= 5 and (max(f_vals) > 0 or max(m_vals) > 0)

    if use_quantiles:
        f20, f40, f60, f80 = _quantile_cutoffs(f_vals, (0.2, 0.4, 0.6, 0.8))
        m20, m40, m60, m80 = _quantile_cutoffs(m_vals, (0.2, 0.4, 0.6, 0.8))
        r20, r40, r60, r80 = _quantile_cutoffs(r_vals, (0.2, 0.4, 0.6, 0.8))

        def score(c: _ClientAgg) -> Tuple[int, int, int]:
            if c.tx_total == 0:
                return (1, 1, 1)
            r = _score_1_5_inverse_by_cutoffs(c.recency_days, r20, r40, r60, r80)
            f = _score_1_5_by_cutoffs(c.tx_90d, f20, f40, f60, f80)
            m = _score_1_5_by_cutoffs(c.spent_90d, m20, m40, m60, m80)
            return (r, f, m)

    else:
        def score(c: _ClientAgg) -> Tuple[int, int, int]:
            if c.tx_total == 0:
                return (1, 1, 1)
            if c.recency_days <= 7:
                r = 5
            elif c.recency_days <= 30:
                r = 4
            elif c.recency_days <= 90:
                r = 3
            elif c.recency_days <= 180:
                r = 2
            else:
                r = 1

            if c.tx_90d >= 8:
                f = 5
            elif c.tx_90d >= 5:
                f = 4
            elif c.tx_90d >= 3:
                f = 3
            elif c.tx_90d >= 2:
                f = 2
            else:
                f = 1

            if c.spent_90d >= 1_500_000:
                m = 5
            elif c.spent_90d >= 800_000:
                m = 4
            elif c.spent_90d >= 300_000:
                m = 3
            elif c.spent_90d >= 100_000:
                m = 2
            else:
                m = 1

            return (r, f, m)

    # подготовим items (фильтры + поиск)
    q_raw = (q or "").strip().lower()
    q_digits = "".join(ch for ch in q_raw if ch.isdigit())

    prepared: List[Dict] = []
    for c in selected:
        r, f, m = score(c)
        item = {
            "phone": c.phone,
            "full_name": c.full_name,
            "tier": c.tier,
            "last_purchase_at": c.last_tx_at,
            "recency_days": int(c.recency_days),
            "purchases_90d": int(c.tx_90d),
            "revenue_90d": int(c.spent_90d),
            "purchases_total": int(c.tx_total),
            "revenue_total": int(c.spent_total),
            "r_score": int(r),
            "f_score": int(f),
            "m_score": int(m),
            "rfm": f"{r}{f}{m}",
        }

        if r_min is not None and item["r_score"] < int(r_min):
            continue
        if f_min is not None and item["f_score"] < int(f_min):
            continue
        if m_min is not None and item["m_score"] < int(m_min):
            continue

        if q_raw:
            name_l = (c.full_name or "").lower()
            phone_digits = "".join(ch for ch in c.phone if ch.isdigit())
            ok = False
            if q_digits and q_digits in phone_digits:
                ok = True
            if not ok and q_raw in c.phone.lower():
                ok = True
            if not ok and name_l and q_raw in name_l:
                ok = True
            if not ok:
                continue

        prepared.append(item)

    s = (sort or "").strip().lower()
    if s in ("spent_total", "revenue_total"):
        prepared.sort(key=lambda x: (x["revenue_total"], x["purchases_total"]), reverse=True)
    elif s in ("spent_90d", "revenue_90d"):
        prepared.sort(key=lambda x: (x["revenue_90d"], x["purchases_90d"]), reverse=True)
    elif s in ("rfm", "rfm_desc"):
        prepared.sort(key=lambda x: int(x["rfm"]), reverse=True)
    elif s in ("recency", "recency_days"):
        prepared.sort(key=lambda x: x["recency_days"])
    else:
        prepared.sort(
            key=lambda x: (x["last_purchase_at"] is None, x["last_purchase_at"] or datetime.min),
            reverse=True,
        )

    total = len(prepared)
    page = prepared[offset: offset + limit]

    titles = {
        "new": "Новые",
        "active": "Активные",
        "sleeping": "Спящие",
        "risk": "В зоне риска",
        "lost": "Потерянные",
        "vip": "VIP",
    }
    seg_title = titles.get(key, key)

    return {
        "segment_key": key,
        "segment_title": seg_title,
        "total": total,
        "items": page,
        "generated_at": now,
        "filters": {
            "r_min": r_min,
            "f_min": f_min,
            "m_min": m_min,
            "q": q,
            "sort": sort,
        },
        "rfm_scoring": "quantiles" if use_quantiles else "thresholds",
    }
