from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.loyalty import LoyaltyRunOut, BirthdayRunOut
from app.services.loyalty import process_bonus_lifecycle, grant_birthday_bonus

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


@router.post("/process", response_model=LoyaltyRunOut)
def process_loyalty(db: Session = Depends(get_db)):
    process_bonus_lifecycle(db)
    return LoyaltyRunOut(status="ok")


@router.post("/birthday/run", response_model=BirthdayRunOut)
def run_birthday_grants(db: Session = Depends(get_db)):
    users = db.scalars(select(User)).all()
    granted = 0
    for u in users:
        g = grant_birthday_bonus(db, u)
        if g:
            granted += 1
    return BirthdayRunOut(status="ok", granted=granted)
