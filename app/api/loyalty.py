# app/api/loyalty.py
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.loyalty import LoyaltyRunOut, BirthdayRunOut
from app.services.loyalty import process_bonus_lifecycle, grant_birthday_bonus

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


@router.post("/process", response_model=LoyaltyRunOut)
def process_loyalty(request: Request, db: Session = Depends(get_db)):
    tenant_id = must_tenant_id(request)
    process_bonus_lifecycle(db, tenant_id=tenant_id)
    return LoyaltyRunOut(status="ok")


@router.post("/birthday/run", response_model=BirthdayRunOut)
def run_birthday_grants(request: Request, db: Session = Depends(get_db)):
    tenant_id = must_tenant_id(request)
    users = db.scalars(select(User).where(User.tenant_id == tenant_id)).all()
    granted = 0
    for u in users:
        g = grant_birthday_bonus(db, u)
        if g:
            granted += 1
    return BirthdayRunOut(status="ok", granted=granted)