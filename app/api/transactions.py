from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionOut

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


@router.post("/", response_model=TransactionOut)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    settings = get_settings(db)

    user_phone = normalize_phone(payload.user_phone)

    user = db.query(User).filter(User.phone == user_phone).first()
    if not user:
        user = User(
            phone=user_phone,
            full_name=payload.full_name or "",
            birth_date=payload.birth_date,
            tier=payload.tier or "Bronze",
            bonus_balance=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # paid_amount — источник правды для тира/начислений
    paid_amount = payload.paid_amount if payload.paid_amount is not None else payload.amount
    paid_amount = int(paid_amount or 0)

    # Балансы (после lifecycle)
    balances = get_balances(db, user_id=user.id)
    active_balance = int(balances["available"])

    # Списание: только из активного, + ограничение % от paid_amount
    cap = redeem_cap(paid_amount, settings)
    requested = int(payload.redeem_points or 0)
    redeem_target = clamp(requested, 0, min(active_balance, cap))
    redeemed = consume_available(db, user_id=user.id, to_spend=redeem_target)

    # Начисление: считаем строго от paid_amount (не от amount)
    # и НЕ уменьшаем paid_amount на redeem (как ты и написал: “класс не в виде накопления…”)
    earned = calc_earn(paid_amount=paid_amount, tier=user.tier, settings=settings)

    txn = Transaction(
        user_id=user.id,
        amount=int(payload.amount or 0),
        paid_amount=paid_amount,
        redeem_points=redeemed,
        earned_points=earned,
        payment_method=payload.payment_method or "OTHER",
        comment=payload.comment or "",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    # Создаем грант на earned (pending/available по activation_days)
    grant_purchase_bonus(db, user_id=user.id, earn=earned, settings=settings)

    # Синхронизируем кэш в users.bonus_balance = активный баланс после списания/начисления
    balances2 = get_balances(db, user_id=user.id)
    user.bonus_balance = int(balances2["available"])
    db.commit()

    out = TransactionOut.model_validate(txn)
    out.user_phone = user.phone
    return out


@router.get("/by-phone/{user_phone}", response_model=List[TransactionOut])
def list_by_phone(user_phone: str, db: Session = Depends(get_db)):
    p = normalize_phone(user_phone)
    user = db.query(User).filter(User.phone == p).first()
    if not user:
        return []

    rows = (
        db.query(Transaction)
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
    phone: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Transaction, User.phone).join(User, User.id == Transaction.user_id)

    if phone:
        p = normalize_phone(phone)
        q = q.filter(User.phone == p)

    rows = q.order_by(desc(Transaction.id)).offset(offset).limit(limit).all()

    out: List[TransactionOut] = []
    for t, user_phone in rows:
        item = TransactionOut.model_validate(t)
        item.user_phone = user_phone or ""
        out.append(item)

    return out
