# app/services/broadcast_audience.py
"""
Сборка аудитории для WhatsApp-рассылок.

Все виды аудитории работают по ОБЩЕЙ базе сети (клиенты хранятся на корне),
транзакционные метрики (неактивность, RFM) считаются по всем филиалам сети.

Всегда исключаются:
  - клиенты с wa_opt_out (отписались от рассылок)
  - клиенты без валидного телефона
  - дубли по phone_hash
  - получавшие рассылку за последние exclude_recent_days дней
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import decrypt_field
from app.models.user import User
from app.models.transaction import Transaction
from app.models.bonus_grant import BonusGrant
from app.models.campaign import CampaignRecipient
from app.models.broadcast import WaMessage
from app.services.whatsapp import normalize_phone

logger = logging.getLogger(__name__)

AUDIENCE_KINDS = ("all", "bonus_gt_zero", "inactive_days", "tier", "segment", "campaign", "manual")


def _now() -> datetime:
    return datetime.utcnow()


def _live_bonus_map(db: Session, user_ids: List[int]) -> Dict[int, int]:
    """Живые доступные бонусы по списку клиентов одним запросом."""
    if not user_ids:
        return {}
    now = _now()
    rows = (
        db.query(BonusGrant.user_id, func.coalesce(func.sum(BonusGrant.remaining), 0))
        .filter(
            BonusGrant.user_id.in_(user_ids),
            BonusGrant.status == "available",
            BonusGrant.expires_at > now,
            BonusGrant.remaining > 0,
        )
        .group_by(BonusGrant.user_id)
        .all()
    )
    return {int(uid): int(total or 0) for uid, total in rows}


def _recent_broadcast_user_ids(db: Session, network_id: int, days: int) -> set[int]:
    """Клиенты, получавшие рассылку сети за последние N дней."""
    if days <= 0:
        return set()
    from app.models.broadcast import Broadcast
    cutoff = _now() - timedelta(days=days)
    rows = (
        db.query(WaMessage.user_id)
        .join(Broadcast, Broadcast.id == WaMessage.broadcast_id)
        .filter(
            Broadcast.network_id == network_id,
            WaMessage.user_id.isnot(None),
            WaMessage.status == "sent",
            WaMessage.sent_at >= cutoff,
            WaMessage.kind == "broadcast",
        )
        .all()
    )
    return {int(r[0]) for r in rows if r[0] is not None}


def build_audience(
    db: Session,
    network_id: int,
    tenant_ids: List[int],
    kind: str,
    params: Optional[Dict[str, Any]] = None,
    exclude_recent_days: int = 7,
) -> Dict[str, Any]:
    """
    Возвращает {"recipients": [...], "excluded": {...}} где recipient =
    {user_id, phone, name, tier, bonus}.
    """
    params = params or {}
    kind = (kind or "all").strip()
    if kind not in AUDIENCE_KINDS:
        raise ValueError(f"Неизвестный тип аудитории: {kind}")

    excluded = {"opt_out": 0, "no_phone": 0, "duplicate": 0, "recent": 0}

    # ── 1. Базовый список клиентов сети ──────────────────────
    users_q = db.query(User).filter(User.tenant_id == network_id)
    users: List[User] = users_q.all()
    users_by_id = {u.id: u for u in users}

    selected_ids: List[int] = []

    if kind == "all":
        selected_ids = list(users_by_id.keys())

    elif kind == "bonus_gt_zero":
        min_bonus = max(1, int(params.get("min_bonus") or 1))
        bonus_map = _live_bonus_map(db, list(users_by_id.keys()))
        selected_ids = [uid for uid, total in bonus_map.items() if total >= min_bonus]

    elif kind == "inactive_days":
        # days     — нижняя граница: не покупал МИНИМУМ столько дней
        # days_max — верхняя граница (необязательно): покупал НЕ РАНЬШЕ чем столько дней назад
        # Волна «4-6 месяцев»: {"days": 122, "days_max": 183}
        days = max(1, int(params.get("days") or 30))
        days_max_raw = params.get("days_max")
        days_max = int(days_max_raw) if days_max_raw not in (None, "", 0) else None
        if days_max is not None and days_max <= days:
            raise ValueError("days_max должен быть больше days")

        now = _now()
        cutoff = now - timedelta(days=days)
        cutoff_max = now - timedelta(days=days_max) if days_max else None

        rows = (
            db.query(Transaction.user_id, func.max(Transaction.created_at))
            .filter(Transaction.tenant_id.in_(tenant_ids))
            .group_by(Transaction.user_id)
            .all()
        )
        last_map = {int(uid): last for uid, last in rows}

        # Никогда не покупавших нельзя отнести к волне по давности —
        # при заданном days_max они исключаются автоматически.
        include_never = bool(params.get("include_never", True)) and days_max is None

        for uid in users_by_id:
            last = last_map.get(uid)
            if last is None:
                if include_never:
                    selected_ids.append(uid)
                continue
            if last >= cutoff:
                continue                      # покупал недавно — не наш
            if cutoff_max is not None and last < cutoff_max:
                continue                      # покупал слишком давно — другая волна
            selected_ids.append(uid)

    elif kind == "tier":
        tier = str(params.get("tier") or "Gold").strip()
        selected_ids = [uid for uid, u in users_by_id.items() if (u.tier or "Bronze") == tier]

    elif kind == "segment":
        from app.services.analytics import list_clients_by_segment
        key = str(params.get("segment") or "all")
        res = list_clients_by_segment(
            db,
            tenant_id=tenant_ids[0],
            key=key,
            limit=100000,
            offset=0,
            tenant_ids=tenant_ids,
            client_tenant_id=network_id,
        )
        phones = {normalize_phone(str(it.get("phone") or "")) for it in (res.get("items") or [])}
        phone_hashes = {hashlib.sha256(p.encode()).hexdigest() for p in phones if p}
        selected_ids = [uid for uid, u in users_by_id.items() if u.phone_hash in phone_hashes]

    elif kind == "campaign":
        campaign_id = int(params.get("campaign_id") or 0)
        rows = (
            db.query(CampaignRecipient.phone)
            .filter(CampaignRecipient.campaign_id == campaign_id)
            .all()
        )
        phones = {normalize_phone(str(r[0] or "")) for r in rows}
        phone_hashes = {hashlib.sha256(p.encode()).hexdigest() for p in phones if p}
        selected_ids = [uid for uid, u in users_by_id.items() if u.phone_hash in phone_hashes]

    elif kind == "manual":
        ids = params.get("user_ids") or []
        selected_ids = [int(i) for i in ids if int(i) in users_by_id]

    # ── 2. Общие исключения ──────────────────────────────────
    recent_ids = _recent_broadcast_user_ids(db, network_id, int(exclude_recent_days or 0))
    bonus_map = _live_bonus_map(db, selected_ids)

    recipients: List[Dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for uid in selected_ids:
        u = users_by_id.get(uid)
        if not u:
            continue
        if bool(getattr(u, "wa_opt_out", False)):
            excluded["opt_out"] += 1
            continue
        if uid in recent_ids:
            excluded["recent"] += 1
            continue

        phone_plain = normalize_phone(decrypt_field(u.phone) or u.phone or "")
        if len(phone_plain) < 10:
            excluded["no_phone"] += 1
            continue

        h = u.phone_hash or hashlib.sha256(phone_plain.encode()).hexdigest()
        if h in seen_hashes:
            excluded["duplicate"] += 1
            continue
        seen_hashes.add(h)

        name = (decrypt_field(u.full_name) or "").strip() if u.full_name else ""
        recipients.append({
            "user_id": uid,
            "phone": phone_plain,
            "name": name or "Клиент",
            "tier": u.tier or "Bronze",
            "bonus": int(bonus_map.get(uid, 0)),
        })

    return {"recipients": recipients, "excluded": excluded}


def estimate_audience(
    db: Session,
    network_id: int,
    tenant_ids: List[int],
    kind: str,
    params: Optional[Dict[str, Any]] = None,
    exclude_recent_days: int = 7,
    sample_size: int = 10,
) -> Dict[str, Any]:
    res = build_audience(
        db,
        network_id=network_id,
        tenant_ids=tenant_ids,
        kind=kind,
        params=params,
        exclude_recent_days=exclude_recent_days,
    )
    recs = res["recipients"]
    return {
        "count": len(recs),
        "excluded": res["excluded"],
        "sample": [
            {"name": r["name"], "phone": r["phone"][-4:].rjust(len(r["phone"]), "*"), "bonus": r["bonus"], "tier": r["tier"]}
            for r in recs[:sample_size]
        ],
    }
