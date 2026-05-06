from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from io import BytesIO

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from openpyxl import Workbook

from app.core.database import get_db
from app.models.bonus_grant import BonusGrant
from app.models.user import User
from app.models.transaction import Transaction

router = APIRouter(prefix="/reports", tags=["reports"])


def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


# ── Отчёт по сгоревшим бонусам ───────────────────────────────
@router.get("/expired-bonuses")
def expired_bonuses(
    request: Request,
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    tenant_id = must_tenant_id(request)

    q = (
        db.query(BonusGrant, User.phone, User.full_name)
        .join(User, User.id == BonusGrant.user_id)
        .filter(BonusGrant.status == "expired")
        .filter(BonusGrant.tenant_id == tenant_id)
    )

    if date_from:
        q = q.filter(func.date(BonusGrant.expires_at) >= date_from)
    if date_to:
        q = q.filter(func.date(BonusGrant.expires_at) <= date_to)

    total = q.count()
    rows = q.order_by(BonusGrant.expires_at.desc()).offset(offset).limit(limit).all()

    items = []
    for grant, phone, name in rows:
        items.append({
            "grant_id": grant.id,
            "user_id": grant.user_id,
            "phone": phone or "",
            "full_name": name or "",
            "amount": int(grant.amount or 0),
            "remaining": int(grant.remaining or 0),
            "burned": int(grant.amount or 0) - int(grant.remaining or 0),
            "expires_at": str(grant.expires_at),
            "source": grant.source or "",
        })

    return {"total": total, "limit": limit, "offset": offset, "items": items}


# ── Отчёт по дням рождениям за месяц ─────────────────────────
@router.get("/birthdays")
def birthdays_report(
    request: Request,
    month: int = Query(..., ge=1, le=12, description="Месяц (1-12)"),
    year: Optional[int] = Query(default=None, description="Год, по умолчанию текущий"),
    db: Session = Depends(get_db),
):
    tenant_id = must_tenant_id(request)
    if not year:
        year = date.today().year

    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id)
        .filter(User.birth_date.isnot(None))
        .filter(extract("month", User.birth_date) == month)
        .order_by(extract("day", User.birth_date))
        .all()
    )

    items = []
    for u in users:
        bd = u.birth_date
        age = year - bd.year if bd else None
        items.append({
            "user_id": u.id,
            "phone": u.phone or "",
            "full_name": u.full_name or "",
            "birth_date": str(bd),
            "day": bd.day if bd else None,
            "age": age,
            "tier": u.tier or "",
            "bonus_balance": int(u.bonus_balance or 0),
        })

    return {"month": month, "year": year, "count": len(items), "items": items}


# ── Экспорт транзакций в Excel ───────────────────────────────
@router.get("/transactions-excel")
def transactions_excel(
    request: Request,
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    tenant_id = must_tenant_id(request)

    q = (
        db.query(Transaction, User.phone, User.full_name)
        .join(User, User.id == Transaction.user_id)
        .filter(Transaction.tenant_id == tenant_id)
    )

    if date_from:
        q = q.filter(func.date(Transaction.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(Transaction.created_at) <= date_to)

    rows = q.order_by(Transaction.created_at.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Транзакции"

    headers = ["ID", "Дата", "Клиент", "Телефон", "Сумма", "Оплачено", "Списано бонусов", "Начислено бонусов", "Метод оплаты", "Статус", "Комментарий"]
    ws.append(headers)

    for tx, phone, name in rows:
        ws.append([
            tx.id,
            str(tx.created_at),
            name or "",
            phone or "",
            int(tx.amount or 0),
            int(tx.paid_amount or 0),
            int(tx.redeem_points or 0),
            int(tx.earned_points or 0),
            tx.payment_method or "",
            tx.status or "",
            tx.comment or "",
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"transactions_{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
