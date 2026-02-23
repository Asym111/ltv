# app/services/analytics.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.user import User

# UTC+5 Алматы
ALMATY = timezone(timedelta(hours=5))


def _utcnow() -> datetime:
    """Текущее время по Алматы (UTC+5), без tzinfo для совместимости с БД."""
    return datetime.now(ALMATY).replace(tzinfo=None)


def _window_stats(db: Session, since: datetime, now: datetime, tenant_id: int) -> Dict[str, Any]:
    txs = (
        db.query(
            func.count(Transaction.id).label("tx_count"),
            func.coalesce(func.sum(Transaction.paid_amount), 0).label("revenue"),
            func.count(func.distinct(Transaction.user_id)).label("clients"),
        )
        .filter(
            Transaction.tenant_id == tenant_id,
            Transaction.created_at >= since,
            Transaction.created_at <= now,
        )
        .first()
    )
    tx_count  = int(txs.tx_count or 0)
    revenue   = int(txs.revenue  or 0)
    clients   = int(txs.clients  or 0)
    avg_check = round(float(revenue / tx_count), 2) if tx_count else 0.0
    return {"revenue": revenue, "transactions": tx_count, "clients": clients, "avg_check": avg_check}


def _daily_revenue(db: Session, since: datetime, now: datetime, tenant_id: int) -> List[Dict[str, Any]]:
    rows = (
        db.query(
            func.date(Transaction.created_at).label("day"),
            func.coalesce(func.sum(Transaction.paid_amount), 0).label("revenue"),
            func.count(Transaction.id).label("tx_count"),
        )
        .filter(
            Transaction.tenant_id == tenant_id,
            Transaction.created_at >= since,
            Transaction.created_at <= now,
        )
        .group_by(func.date(Transaction.created_at))
        .order_by(func.date(Transaction.created_at))
        .all()
    )
    return [{"day": str(r.day), "revenue": int(r.revenue or 0), "tx_count": int(r.tx_count or 0)} for r in rows]


def _rfm_score(recency_days: int, freq: int, monetary: int) -> tuple[int, int, int]:
    if recency_days <= 7:    r = 5
    elif recency_days <= 14: r = 4
    elif recency_days <= 30: r = 3
    elif recency_days <= 60: r = 2
    else:                    r = 1

    if freq >= 10:  f = 5
    elif freq >= 5: f = 4
    elif freq >= 3: f = 3
    elif freq >= 2: f = 2
    else:           f = 1

    if monetary >= 500_000:   m = 5
    elif monetary >= 200_000: m = 4
    elif monetary >= 100_000: m = 3
    elif monetary >= 50_000:  m = 2
    else:                     m = 1
    return r, f, m


SEGMENT_DEFS = {
    "vip":    {"title": "VIP клиенты",   "hint": "R≥4, F≥4, M≥4 — лучшие клиенты"},
    "active": {"title": "Активные",      "hint": "R≥3, F≥2 — регулярные покупатели"},
    "risk":   {"title": "Риск оттока",   "hint": "R=2 — давно не покупали"},
    "lost":   {"title": "Потерянные",    "hint": "R=1 — очень давно не покупали"},
    "new":    {"title": "Новые",         "hint": "F=1 — только первая покупка"},
    "all":    {"title": "Все клиенты",   "hint": "Полная база"},
}


def _segment_matches(key: str, r: int, f: int, m: int, purchases_total: int) -> bool:
    if key == "all":    return True
    if key == "vip":    return r >= 4 and f >= 4 and m >= 4
    if key == "active": return r >= 3 and f >= 2
    if key == "risk":   return r == 2
    if key == "lost":   return r == 1
    if key == "new":    return purchases_total == 1
    return False


def build_analytics_overview(db: Session, tenant_id: int) -> Dict[str, Any]:
    now = _utcnow()
    windows_raw = [
        (7,  "7 дней",  now - timedelta(days=7)),
        (30, "30 дней", now - timedelta(days=30)),
        (90, "90 дней", now - timedelta(days=90)),
    ]
    windows = []
    for days, label, since in windows_raw:
        stats = _window_stats(db, since, now, tenant_id)
        windows.append({"days": days, "label": label, **stats})

    daily_30 = _daily_revenue(db, now - timedelta(days=30), now, tenant_id)

    clients_total = int(db.query(func.count(User.id)).filter(User.tenant_id == tenant_id).scalar() or 0)
    users_with_tx = int(
        db.query(func.count(func.distinct(Transaction.user_id)))
        .filter(Transaction.tenant_id == tenant_id).scalar() or 0
    )
    total_spent = int(
        db.query(func.coalesce(func.sum(Transaction.paid_amount), 0))
        .filter(Transaction.tenant_id == tenant_id).scalar() or 0
    )

    since_90 = now - timedelta(days=90)
    freq_rows = (
        db.query(
            Transaction.user_id.label("uid"),
            func.count(Transaction.id).label("freq"),
            func.coalesce(func.sum(Transaction.paid_amount), 0).label("monetary"),
            func.max(Transaction.created_at).label("last_tx"),
        )
        .filter(Transaction.tenant_id == tenant_id, Transaction.created_at >= since_90)
        .group_by(Transaction.user_id)
        .all()
    )
    total_freq_rows = (
        db.query(Transaction.user_id.label("uid"), func.count(Transaction.id).label("total"))
        .filter(Transaction.tenant_id == tenant_id)
        .group_by(Transaction.user_id)
        .all()
    )
    total_freq_map = {r.uid: int(r.total) for r in total_freq_rows}

    segment_counts: Dict[str, int] = {k: 0 for k in SEGMENT_DEFS}
    for row in freq_rows:
        recency_days = (now - row.last_tx).days if row.last_tx else 999
        r, f, m = _rfm_score(recency_days, int(row.freq or 0), int(row.monetary or 0))
        purchases_total = total_freq_map.get(row.uid, 1)
        for seg_key in SEGMENT_DEFS:
            if seg_key == "all":
                continue
            if _segment_matches(seg_key, r, f, m, purchases_total):
                segment_counts[seg_key] += 1
    segment_counts["all"] = clients_total

    segments = [
        {"key": k, "title": SEGMENT_DEFS[k]["title"], "hint": SEGMENT_DEFS[k]["hint"], "clients": segment_counts.get(k, 0)}
        for k in SEGMENT_DEFS
    ]

    alerts = []
    if segment_counts.get("risk", 0) > 0:
        alerts.append({"key": "risk", "title": f"{segment_counts['risk']} клиентов в зоне риска", "level": "warning", "count": segment_counts["risk"], "hint": "Не покупали 30-60 дней.", "href": "/admin/analytics/segment/risk"})
    if segment_counts.get("lost", 0) > 0:
        alerts.append({"key": "lost", "title": f"{segment_counts['lost']} потерянных клиентов", "level": "danger", "count": segment_counts["lost"], "hint": "Не покупали более 60 дней.", "href": "/admin/analytics/segment/lost"})
    if segment_counts.get("new", 0) > 0:
        alerts.append({"key": "new", "title": f"{segment_counts['new']} новых клиентов", "level": "info", "count": segment_counts["new"], "hint": "Только одна покупка — важно удержать.", "href": "/admin/analytics/segment/new"})

    return {
        "generated_at":  now.isoformat(),
        "windows":       windows,
        "segments":      segments,
        "alerts":        alerts,
        "clients_total": clients_total,
        "users_with_tx": users_with_tx,
        "total_spent":   total_spent,
        "daily_30":      daily_30,
    }


def list_clients_by_segment(
    db: Session,
    tenant_id: int,
    key: str,
    limit: int = 200,
    offset: int = 0,
    r_min: Optional[int] = None,
    f_min: Optional[int] = None,
    m_min: Optional[int] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
) -> Dict[str, Any]:
    now = _utcnow()
    since_90 = now - timedelta(days=90)
    seg_info = SEGMENT_DEFS.get(key, {"title": key, "hint": ""})

    freq_rows = (
        db.query(
            Transaction.user_id.label("uid"),
            func.count(Transaction.id).label("freq_90"),
            func.coalesce(func.sum(Transaction.paid_amount), 0).label("rev_90"),
            func.max(Transaction.created_at).label("last_tx"),
        )
        .filter(Transaction.tenant_id == tenant_id, Transaction.created_at >= since_90)
        .group_by(Transaction.user_id)
        .all()
    )
    total_rows = (
        db.query(
            Transaction.user_id.label("uid"),
            func.count(Transaction.id).label("total_freq"),
            func.coalesce(func.sum(Transaction.paid_amount), 0).label("total_rev"),
        )
        .filter(Transaction.tenant_id == tenant_id)
        .group_by(Transaction.user_id)
        .all()
    )
    total_map = {r.uid: (int(r.total_freq), int(r.total_rev)) for r in total_rows}
    users_map = {u.id: u for u in db.query(User).filter(User.tenant_id == tenant_id).all()}
    freq_map_90 = {r.uid: r for r in freq_rows}
    uid_set = set(users_map.keys()) if key == "all" else set(freq_map_90.keys())

    results = []
    for uid in uid_set:
        user = users_map.get(uid)
        if not user:
            continue
        row = freq_map_90.get(uid)
        if row:
            recency_days = (now - row.last_tx).days if row.last_tx else 999
            freq_90 = int(row.freq_90 or 0)
            rev_90  = int(row.rev_90  or 0)
            last_tx = row.last_tx
        else:
            recency_days = 999
            freq_90 = 0
            rev_90  = 0
            last_tx = None

        total_freq, total_rev = total_map.get(uid, (0, 0))
        r, f, m = _rfm_score(recency_days, freq_90, rev_90)

        if key != "all" and not _segment_matches(key, r, f, m, total_freq):
            continue
        if r_min and r < r_min: continue
        if f_min and f < f_min: continue
        if m_min and m < m_min: continue
        if q:
            q_low = q.lower()
            if (user.full_name or "").lower().find(q_low) == -1 and (user.phone or "").find(q_low) == -1:
                continue

        results.append({
            "phone":            user.phone,
            "full_name":        user.full_name,
            "tier":             user.tier or "Bronze",
            "last_purchase_at": last_tx.isoformat() if last_tx else None,
            "recency_days":     recency_days,
            "purchases_90d":    freq_90,
            "revenue_90d":      rev_90,
            "purchases_total":  total_freq,
            "revenue_total":    total_rev,
            "r_score":          r,
            "f_score":          f,
            "m_score":          m,
            "rfm":              f"{r}{f}{m}",
        })

    sort_key = sort or "revenue_total"
    reverse  = True
    if sort_key.startswith("-"):
        sort_key = sort_key[1:]
        reverse  = False
    if sort_key not in {"recency_days", "revenue_90d", "revenue_total", "purchases_total", "rfm"}:
        sort_key = "revenue_total"
    results.sort(key=lambda x: x.get(sort_key, 0) or 0, reverse=reverse)

    return {
        "segment_key":   key,
        "segment_title": seg_info["title"],
        "total":         len(results),
        "items":         results[offset: offset + limit],
        "generated_at":  now.isoformat(),
        "filters":       {"r_min": r_min, "f_min": f_min, "m_min": m_min, "q": q, "sort": sort},
        "rfm_scoring":   "R: recency 90d | F: freq 90d | M: monetary 90d | 1=low 5=high",
    }
