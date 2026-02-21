from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, select

from app.core.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.models.bonus_grant import BonusGrant
from app.schemas.transaction import TransactionCreate, TransactionOut, TransactionRefund

from app.services.loyalty_engine import (
    get_settings,
    get_balances,
    redeem_cap,
    consume_available,
    calc_earn,
    grant_purchase_bonus,
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


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(n, hi))


def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


@router.post("/", response_model=TransactionOut)
def create_transaction(payload: TransactionCreate, request: Request, db: Session = Depends(get_db)):
    tenant_id = must_tenant_id(request)
    settings = get_settings(db)

    user_phone = normalize_phone(payload.user_phone)

    user = (
        db.query(User)
        .filter(User.tenant_id == tenant_id)
        .filter(User.phone == user_phone)
        .first()
    )
    if not user:
        user = User(
            tenant_id=tenant_id,
            phone=user_phone,
            full_name=payload.full_name or "",
            birth_date=payload.birth_date,
            tier=payload.tier or "Bronze",
            bonus_balance=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    paid_amount = payload.paid_amount if payload.paid_amount is not None else payload.amount
    paid_amount = int(paid_amount or 0)

    balances = get_balances(db, user_id=user.id)
    active_balance = int(balances["available"])  # только активированные — можно списать

    cap = redeem_cap(paid_amount, settings)
    requested = int(payload.redeem_points or 0)

    # Жёсткий двойной лимит: не больше баланса И не больше % от чека
    # consume_available дополнительно защищён SELECT FOR UPDATE
    redeem_target = clamp(requested, 0, min(active_balance, cap))
    redeemed = consume_available(db, user_id=user.id, to_spend=redeem_target)

    # Защита: если реально списано меньше (race condition) — пересчитываем
    if redeemed > active_balance:
        redeemed = active_balance  # не может случиться, но страховка

    earned = calc_earn(paid_amount=paid_amount, tier=user.tier, settings=settings)

    txn = Transaction(
        tenant_id=tenant_id,
        user_id=user.id,
        amount=int(payload.amount or 0),
        paid_amount=paid_amount,
        redeem_points=redeemed,
        earned_points=earned,
        payment_method=payload.payment_method or "OTHER",
        comment=payload.comment or "",
        status="completed",
        refunded_amount=0,
        refunded_at=None,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    # ✅ начисление бонусов привязываем к txn.id
    grant_purchase_bonus(db, user_id=user.id, earn=earned, settings=settings, txn_id=txn.id)

    balances2 = get_balances(db, user_id=user.id)
    # bonus_balance = total (available + pending) — клиент видит все свои бонусы
    # Списывать можно только available, но показываем всё
    user.bonus_balance = int(balances2["total"])
    db.commit()

    out = TransactionOut.model_validate(txn)
    out.user_phone = user.phone
    return out


@router.post("/{tx_id}/refund", response_model=TransactionOut)
def refund_transaction(tx_id: int, payload: TransactionRefund, request: Request, db: Session = Depends(get_db)):
    tenant_id = must_tenant_id(request)
    settings = get_settings(db)
    now = datetime.utcnow()

    tx = (
        db.query(Transaction)
        .filter(Transaction.tenant_id == tenant_id)
        .filter(Transaction.id == tx_id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if tx.status == "refunded":
        raise HTTPException(status_code=400, detail="Transaction already fully refunded")

    if tx.paid_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid paid_amount for refund")

    # Определяем сумму возврата
    if payload.full_refund:
        refund_amount = tx.paid_amount - int(tx.refunded_amount or 0)
    else:
        if not payload.amount:
            raise HTTPException(status_code=400, detail="amount is required for partial refund")
        refund_amount = int(payload.amount)

    refundable_left = tx.paid_amount - int(tx.refunded_amount or 0)
    refund_amount = clamp(refund_amount, 1, max(0, refundable_left))
    if refund_amount <= 0:
        raise HTTPException(status_code=400, detail="Nothing to refund")

    # Пропорции
    ratio_num = refund_amount
    ratio_den = tx.paid_amount

    earned_revert = int((tx.earned_points * ratio_num) // ratio_den) if tx.earned_points > 0 else 0
    redeem_return = int((tx.redeem_points * ratio_num) // ratio_den) if tx.redeem_points > 0 else 0

    user = (
        db.query(User)
        .filter(User.tenant_id == tenant_id)
        .filter(User.id == tx.user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1) Возвращаем списанные бонусы клиенту (redeem_return)
    if redeem_return > 0:
        available_from = now  # сразу доступно
        expires_at = now + timedelta(days=int(settings.burn_days))  # тот же burn_days
        g = BonusGrant(
            user_id=user.id,
            transaction_id=tx.id,
            amount=redeem_return,
            remaining=redeem_return,
            status="available",
            available_from=available_from,
            expires_at=expires_at,
            source="refund_redeem",
        )
        db.add(g)
        db.commit()

    # 2) Забираем начисленные за покупку бонусы (earned_revert)
    if earned_revert > 0:
        grant = db.scalar(
            select(BonusGrant).where(
                BonusGrant.user_id == user.id,
                BonusGrant.transaction_id == tx.id,
                BonusGrant.source == "purchase",
            )
        )
        shortfall = earned_revert

        if grant:
            take = min(int(grant.remaining or 0), shortfall)
            grant.remaining = int(grant.remaining or 0) - take
            shortfall -= take
            if grant.remaining <= 0:
                grant.remaining = 0
                grant.status = "expired"
            db.commit()

        # если начисление уже потрачено — докусываем из текущего available (чтобы баланс стал корректным)
        if shortfall > 0:
            consume_available(db, user_id=user.id, to_spend=shortfall)

    # 3) Фиксируем состояние транзакции
    tx.refunded_amount = int(tx.refunded_amount or 0) + refund_amount
    tx.refunded_at = now
    if tx.refunded_amount >= tx.paid_amount:
        tx.status = "refunded"
    else:
        tx.status = "partially_refunded"

    # можно сохранить комментарий в tx.comment (без отдельного поля)
    if payload.comment:
        base = (tx.comment or "").strip()
        add = f"[REFUND {refund_amount}] {payload.comment}".strip()
        tx.comment = (base + " " + add).strip() if base else add

    db.commit()

    # 4) Обновляем баланс на пользователе
    # Обновляем баланс на пользователе (total = available + pending)
    balances2 = get_balances(db, user_id=user.id)
    user.bonus_balance = int(balances2["total"])
    db.commit()

    out = TransactionOut.model_validate(tx)
    out.user_phone = user.phone
    return out


@router.get("/by-phone/{user_phone}", response_model=List[TransactionOut])
def list_by_phone(user_phone: str, request: Request, db: Session = Depends(get_db)):
    tenant_id = must_tenant_id(request)

    p = normalize_phone(user_phone)
    user = (
        db.query(User)
        .filter(User.tenant_id == tenant_id)
        .filter(User.phone == p)
        .first()
    )
    if not user:
        return []

    rows = (
        db.query(Transaction)
        .filter(Transaction.tenant_id == tenant_id)
        .filter(Transaction.user_id == user.id)
        .order_by(desc(Transaction.id))
        .all()
    )

    out: List[TransactionOut] = []
    for t in rows:
        item = TransactionOut.model_validate(t)
        item.user_phone = user.phone
        out.append(item)
    return out


@router.get("", response_model=List[TransactionOut], include_in_schema=False)
@router.get("/", response_model=List[TransactionOut])
def list_transactions(
    request: Request,
    phone: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    tenant_id = must_tenant_id(request)

    q = (
        db.query(Transaction, User.phone)
        .join(User, User.id == Transaction.user_id)
        .filter(Transaction.tenant_id == tenant_id)
        .filter(User.tenant_id == tenant_id)
    )

    if phone:
        p = normalize_phone(phone)
        q = q.filter(User.phone == p)

    # Фильтрация по календарным датам (включительно)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(Transaction.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            # Берём конец дня — до 23:59:59
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
        item.user_phone = user_phone or ""
        out.append(item)

    return out