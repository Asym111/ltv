# app/api/crm.py
from __future__ import annotations

import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.core.database import get_db
from app.core.security import decrypt_field
from app.core.roles import TRANSACTION_ROLES
from app.core.tenant_utils import must_network_id
from app.models.user import User
from app.models.transaction import Transaction
from app.schemas.crm import ClientMetricsOut
from app.services.loyalty_engine import get_balances

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


def require_role(request: Request, *allowed: str):
    u = getattr(request.state, "user", None) or {}
    if u.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    return u


@router.get("/client/{phone}", response_model=ClientMetricsOut)
def get_client_metrics(phone: str, request: Request, db: Session = Depends(get_db)) -> ClientMetricsOut:
    require_role(request, *TRANSACTION_ROLES)
    network_id = must_network_id(request)  # клиент и его история общие на сеть
    p = normalize_phone(phone)
    p_hash = hashlib.sha256(p.encode()).hexdigest()
    user = db.query(User).filter(User.tenant_id == network_id, User.phone_hash == p_hash).first()
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

    # Покупки клиента по всей сети (кошелёк общий)
    total_spent, purchases_count = (
        db.query(total_spent_expr, purchases_count_expr)
        .filter(Transaction.user_id == user.id)
        .first()
    )

    total_spent = int(total_spent or 0)
    purchases_count = int(purchases_count or 0)
    avg_check = (total_spent / purchases_count) if purchases_count else 0.0
    bonus_balance = int(user.bonus_balance or 0)

    balances = get_balances(db, user_id=user.id)

    return ClientMetricsOut(
        id=user.id,
        phone=decrypt_field(user.phone) or user.phone,
        full_name=decrypt_field(user.full_name) if user.full_name else None,
        tier=(user.tier or "Bronze"),
        birth_date=user.birth_date,
        wa_opt_out=bool(getattr(user, "wa_opt_out", False)),
        total_spent=total_spent,
        purchases_count=purchases_count,
        avg_check=round(float(avg_check), 2),
        bonus_balance=int(balances["available"]),
        pending_balance=int(balances["pending"]),
    )