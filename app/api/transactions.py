from __future__ import annotations

import hashlib
import logging
from app.core.security import decrypt_field

from typing import List, Optional
from datetime import datetime


from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.roles import TRANSACTION_ROLES, CLIENT_ACCESS_ROLES
from app.core.tenant_utils import must_network_id, get_tenant_ids_for_user
from app.models.transaction import Transaction
from app.models.user import User
from app.models.refund import RefundRecord
from app.schemas.transaction import TransactionCreate, TransactionOut, TransactionRefund, RedeemPreviewOut, RefundOut

from app.services.loyalty_engine import (
    get_settings,
    get_balances,
    redeem_cap,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def normalize_phone(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("8") and len(s) == 11:
        s = "7" + s[1:]
    if len(s) == 10:
        s = "7" + s
    s = "".join(ch for ch in s if ch.isdigit())
    if len(s) > 11:
        s = s[-11:]
    return s


def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


def require_role(request: Request, *allowed: str):
    u = getattr(request.state, "user", None) or {}
    role = u.get("role", "")
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Access denied. Required roles: {allowed}")
    return u


@router.get("/earning-options")
def earning_options(request: Request, db: Session = Depends(get_db)):
    require_role(request, *TRANSACTION_ROLES)
    settings = get_settings(db, tenant_id=must_tenant_id(request))
    return {"earning_mode": settings.earning_mode}


@router.get("/redeem-preview", response_model=RedeemPreviewOut)
def redeem_preview(
    request: Request,
    phone: str = Query(..., min_length=5),
    amount: int = Query(default=0, ge=0, description="Сумма чека"),
    paid_amount: Optional[int] = Query(default=None, ge=0),
    db: Session = Depends(get_db),
):
    """Максимум к списанию на этот чек: min(активные бонусы, redeem_max_percent% от оплаты)."""
    tenant_id = must_tenant_id(request)
    network_id = must_network_id(request)
    require_role(request, *TRANSACTION_ROLES)
    settings = get_settings(db, tenant_id=tenant_id)

    pct = int(getattr(settings, "redeem_max_percent", 0) or 0)
    paid = int(paid_amount if paid_amount is not None else amount)
    cap = redeem_cap(paid, settings)

    p_hash = hashlib.sha256(normalize_phone(phone).encode()).hexdigest()
    user = (
        db.query(User)
        .filter(User.tenant_id == network_id)
        .filter(User.phone_hash == p_hash)
        .first()
    )
    if not user:
        return RedeemPreviewOut(found=False, redeem_max_percent=pct, cap=cap,
                                earning_mode=settings.earning_mode)

    balances = get_balances(db, user_id=user.id)
    available = int(balances.get("available") or 0)
    return RedeemPreviewOut(
        found=True,
        earning_mode=settings.earning_mode,
        available=available,
        pending=int(balances.get("pending") or 0),
        redeem_max_percent=pct,
        cap=cap,
        max_redeem=max(0, min(available, cap)),
    )


@router.post("/", response_model=TransactionOut)
def create_transaction(payload: TransactionCreate, request: Request, db: Session = Depends(get_db)):
    from app.services.transaction_operations import create_purchase
    tenant_id = must_tenant_id(request)
    require_role(request, *TRANSACTION_ROLES)
    tx, user, balances, created = create_purchase(
        db, payload, tenant_id, must_network_id(request),
        request.state.user.get("id"), normalize_phone(payload.user_phone),
    )
    if created and (tx.redeem_points or tx.earned_points):
        _notify(db, tx, user, balances, (
            f"Спасибо за покупку! Списано {tx.redeem_points}, "
            f"начислено {tx.earned_points} бонусов. Баланс: {balances['total']}."
        ))
    return _transaction_out(tx, user)


@router.post("/{tx_id}/refund", response_model=TransactionOut)
def refund_transaction(tx_id: int, payload: TransactionRefund, request: Request, db: Session = Depends(get_db)):
    from app.services.transaction_operations import refund_purchase
    must_tenant_id(request)
    require_role(request, *CLIENT_ACCESS_ROLES)
    tx, user, balances, record = refund_purchase(
        db, tx_id, payload, get_tenant_ids_for_user(request, db),
        must_network_id(request), request.state.user.get("id"),
    )
    if record is not None:
        _notify(db, tx, user, balances, (
            f"Возврат на {record.amount}₸. Возвращено {record.redeemed_restored}, "
            f"отменено {record.earned_reversed} бонусов. Баланс: {balances['total']}."
        ))
    return _transaction_out(tx, user)


@router.get("/{tx_id}/refunds", response_model=List[RefundOut])
def refund_history(tx_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, *CLIENT_ACCESS_ROLES)
    allowed_ids = get_tenant_ids_for_user(request, db)
    tx = db.query(Transaction).join(User).filter(
        Transaction.id == tx_id, Transaction.tenant_id.in_(allowed_ids),
        User.tenant_id == must_network_id(request),
    ).first()
    if tx is None:
        raise HTTPException(404, detail="Транзакция не найдена")
    return db.query(RefundRecord).filter(RefundRecord.transaction_id == tx.id).order_by(RefundRecord.id).all()


def _transaction_out(tx, user):
    out = TransactionOut.model_validate(tx)
    out.user_phone = decrypt_field(user.phone) or user.phone
    return out


def _notify(db, tx, user, balances, message):
    if not user.phone:
        return
    try:
        from app.services.notify_queue import enqueue_notification, PRIORITY_TRANSACTIONAL
        enqueue_notification(
            db, tenant_id=tx.tenant_id, phone=decrypt_field(user.phone) or user.phone,
            text_=message, user_id=user.id, priority=PRIORITY_TRANSACTIONAL,
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("Transaction notification failed")


@router.get("/by-phone/{user_phone}", response_model=List[TransactionOut])
def list_by_phone(user_phone: str, request: Request, db: Session = Depends(get_db)):
    network_id = must_network_id(request)
    require_role(request, *TRANSACTION_ROLES)

    p = normalize_phone(user_phone)
    p_hash = hashlib.sha256(p.encode()).hexdigest()
    user = (
        db.query(User)
        .filter(User.tenant_id == network_id)
        .filter(User.phone_hash == p_hash)
        .first()
    )
    if not user:
        return []

    # История клиента по всей сети (карточка клиента)
    rows = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(desc(Transaction.id))
        .all()
    )

    out: List[TransactionOut] = []
    for t in rows:
        item = TransactionOut.model_validate(t)
        item.user_phone = decrypt_field(user.phone) or user.phone
        out.append(item)
    return out


@router.get("", response_model=List[TransactionOut], include_in_schema=False)
@router.get("/", response_model=List[TransactionOut])
def list_transactions(
    request: Request,
    phone: Optional[str] = Query(default=None),
    tx_id: Optional[int] = Query(default=None, description="Точный поиск по ID транзакции"),
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    all_branches: bool = Query(default=True, description="Искать по всем доступным филиалам сети"),
    db: Session = Depends(get_db),
):
    tenant_id = must_tenant_id(request)
    require_role(request, *TRANSACTION_ROLES)

    # Область поиска: по умолчанию — все филиалы, доступные пользователю.
    # Иначе транзакции, пробитые в другом филиале, не находятся вообще.
    allowed_ids = get_tenant_ids_for_user(request, db)
    scope_ids = allowed_ids if all_branches else [tenant_id]

    q = (
        db.query(Transaction, User.phone)
        .join(User, User.id == Transaction.user_id)
        .filter(Transaction.tenant_id.in_(scope_ids))
        .filter(User.tenant_id == must_network_id(request))
    )

    if tx_id:
        # Поиск по ID — точечный, остальные фильтры (телефон/даты) не применяем,
        # чтобы транзакция находилась даже если она очень старая.
        q = q.filter(Transaction.id == int(tx_id))
        rows = q.all()
        out: List[TransactionOut] = []
        for t, user_phone in rows:
            item = TransactionOut.model_validate(t)
            item.user_phone = decrypt_field(user_phone) or user_phone or ""
            out.append(item)
        return out

    if phone:
        p = normalize_phone(phone)
        p_hash = hashlib.sha256(p.encode()).hexdigest()
        q = q.filter(User.phone_hash == p_hash)

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(Transaction.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            q = q.filter(Transaction.created_at <= dt_to)
        except ValueError:
            pass

    rows = q.order_by(desc(Transaction.id)).offset(offset).limit(limit).all()

    out: List[TransactionOut] = []
    for t, user_phone in rows:
        item = TransactionOut.model_validate(t)
        item.user_phone = decrypt_field(user_phone) or user_phone or ""
        out.append(item)

    return out
