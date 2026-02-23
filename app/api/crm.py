# app/api/crm.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, case

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


def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


@router.get("/client/{phone}", response_model=ClientMetricsOut)
def get_client_metrics(phone: str, request: Request, db: Session = Depends(get_db)) -> ClientMetricsOut:
    tenant_id = must_tenant_id(request)
    p = normalize_phone(phone)
    user = db.query(User).filter(User.tenant_id == tenant_id, User.phone == p).first()
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")

    paid = func.coalesce(Transaction.paid_amount, 0)
    refunded = func.coalesce(Transaction.refunded_amount, 0)
    net_paid = (paid - refunded)

    total_spent_expr = func.coalesce(
        func.sum(case((net_paid > 0, net_paid), else_=0)), 0
    )
    purchases_count_expr = func.coalesce(
        func.sum(case((net_paid > 0, 1), else_=0)), 0
    )

    total_spent, purchases_count = (
        db.query(total_spent_expr, purchases_count_expr)
        .filter(Transaction.user_id == user.id, Transaction.tenant_id == tenant_id)
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