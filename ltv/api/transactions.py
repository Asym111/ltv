from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.models.bonus import BonusLedger
from app.schemas.transaction import TransactionCreate, TransactionOut
from app.services.loyalty import calc_bonus

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post("", response_model=TransactionOut)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.phone == payload.user_phone)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tx = Transaction(
        user_id=user.id,
        amount=payload.amount,
        currency=payload.currency,
    )
    db.add(tx)

    # начисление бонусов
    bonus = calc_bonus(Decimal(str(payload.amount)), user.loyalty_tier)
    if bonus > 0:
        ledger = BonusLedger(
            user_id=user.id,
            delta=float(bonus),
            reason=f"Cashback {user.loyalty_tier}",
        )
        db.add(ledger)

    db.commit()
    db.refresh(tx)
    return tx


@router.get("/bonus-balance/{user_phone}")
def get_bonus_balance(user_phone: str, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.phone == user_phone)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    balance = db.execute(
        select(func.coalesce(func.sum(BonusLedger.delta), 0)).where(BonusLedger.user_id == user.id)
    ).scalar_one()

    return {"user_id": user.id, "balance": float(balance)}
