from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.schemas.crm import ClientMetricsOut

router = APIRouter(prefix="/crm", tags=["crm"])


def normalize_phone(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if s.startswith("+"):
        s = s[1:]
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) > 11:
        digits = digits[-11:]
    return digits


@router.get("/client/{phone}", response_model=ClientMetricsOut)
def get_client_metrics(phone: str, db: Session = Depends(get_db)) -> ClientMetricsOut:
    p = normalize_phone(phone)
    user = db.query(User).filter(User.phone == p).first()
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")

    total_spent, purchases_count = (
        db.query(
            func.coalesce(func.sum(Transaction.paid_amount), 0),
            func.count(Transaction.id),
        )
        .filter(Transaction.user_id == user.id)
        .first()
    )

    total_spent = int(total_spent or 0)
    purchases_count = int(purchases_count or 0)
    avg_check = (total_spent / purchases_count) if purchases_count else 0.0

    bonus_balance = int(user.bonus_balance or 0)

    return ClientMetricsOut(
        phone=user.phone,
        full_name=(user.full_name or None),
        tier=(user.tier or "Bronze"),
        total_spent=total_spent,
        purchases_count=purchases_count,
        avg_check=round(float(avg_check), 2),
        bonus_balance=bonus_balance,
    )
